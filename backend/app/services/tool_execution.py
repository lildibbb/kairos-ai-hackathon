"""Two-phase, permission-checked agent tool execution.

Proposal and confirmation are separate steps: a proposal never changes device
state, and confirmation re-checks authorization and parameters before the
simulator runs. Replaying a confirmation for an already-finished proposal is
idempotent and does not execute twice.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai import tool_executor, tool_registry
from app.auth.dependencies import AuthenticatedUser
from app.auth.policy import require_assigned_ticket, require_customer_scope
from sqlalchemy import select

from app.domain.models import AuditEvent, Customer, NetworkDevice, Router, Ticket, ToolExecution

PROPOSED = "proposed"
SUCCEEDED = "succeeded"
FAILED = "failed"

TICKET_FULL_SCOPE_ROLES = ("operator", "supervisor")


class ToolNotFoundError(Exception):
    pass


class ToolForbiddenError(Exception):
    pass


class ToolValidationError(Exception):
    pass


@dataclass(frozen=True)
class ToolCatalogItem:
    name: str
    title: str
    description: str
    kind: str
    category: str
    risk: str
    requires_confirmation: bool
    target_device_types: tuple[str, ...] | None


@dataclass(frozen=True)
class ToolProposalRecord:
    id: str
    ticket_id: str
    tool_name: str
    device_id: str
    device_ref: str
    kind: str
    requires_confirmation: bool
    parameters: dict
    status: str
    summary: str
    correlation_id: str
    created_at: datetime
    result: dict | None = None


@dataclass(frozen=True)
class ToolExecutionRecord:
    id: str
    ticket_id: str
    tool_name: str
    device_id: str
    device_ref: str
    status: str
    message: str
    correlation_id: str
    executed_at: datetime
    result: dict | None = None


def catalog(actor: AuthenticatedUser) -> list[ToolCatalogItem]:
    return [
        ToolCatalogItem(
            name=spec.name,
            title=spec.title,
            description=spec.description,
            kind=spec.kind,
            category=spec.category,
            risk=spec.risk,
            requires_confirmation=spec.requires_confirmation,
            target_device_types=spec.target_device_types,
        )
        for spec in tool_registry.catalog_for_role(actor.role)
    ]


def propose_tool(
    session: Session,
    ticket_id: str,
    actor: AuthenticatedUser,
    tool_name: str,
    parameters: dict,
    *,
    evidence_chunk_ids: list[str] | None = None,
) -> ToolProposalRecord:
    spec = tool_registry.get_tool_spec(tool_name)
    if spec is None:
        raise ToolNotFoundError(tool_name)
    if actor.role not in spec.allowed_roles:
        raise ToolForbiddenError(tool_name)

    ticket = _authorize_ticket(session, ticket_id, actor)
    params = _validate_params(spec, parameters)
    device = _authorize_device(session, ticket, spec, params.device_id)

    if spec.requires_confirmation is False:
        result = _run(session, spec.name, device, params)
        row = ToolExecution(
            ticket_id=ticket.id,
            actor_id=actor.id,
            tool_name=spec.name,
            parameters=params.model_dump(),
            outcome=SUCCEEDED if result.succeeded else FAILED,
            message=result.message[:400],
            result=_result_payload(result),
            correlation_id=str(uuid.uuid4()),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor_id=actor.id,
            ticket_id=ticket.id,
            event_type="tool_executed",
            details={
                "tool_name": spec.name,
                "device_ref": device.device_ref,
                "parameters": params.model_dump(),
                "outcome": row.outcome,
                "message": result.message,
                "correlation_id": row.correlation_id,
            },
        )
        session.commit()
        record = _proposal_record(row, device, spec)
        return ToolProposalRecord(
            **{**record.__dict__, "status": row.outcome, "summary": result.message}
        )

    row = ToolExecution(
        ticket_id=ticket.id,
        actor_id=actor.id,
        tool_name=spec.name,
        parameters=params.model_dump(),
        outcome=PROPOSED,
        correlation_id=str(uuid.uuid4()),
    )
    session.add(row)
    session.flush()
    _audit(
        session,
        actor_id=actor.id,
        ticket_id=ticket.id,
        event_type="tool_proposed",
        details={
            "tool_name": spec.name,
            "device_ref": device.device_ref,
            "parameters": params.model_dump(),
            "proposal_id": row.id,
            "evidence_chunk_ids": evidence_chunk_ids or [],
        },
    )
    session.commit()
    return _proposal_record(row, device, spec)


def confirm_tool(
    session: Session,
    ticket_id: str,
    proposal_id: str,
    actor: AuthenticatedUser,
    confirmation_id: str,
) -> ToolExecutionRecord:
    row = session.get(ToolExecution, proposal_id)
    if row is None or row.ticket_id != ticket_id:
        raise ToolNotFoundError(proposal_id)

    spec = tool_registry.get_tool_spec(row.tool_name)
    if spec is None:
        raise ToolNotFoundError(row.tool_name)

    ticket = _authorize_ticket(session, ticket_id, actor)
    if row.actor_id != actor.id or actor.role not in spec.allowed_roles:
        raise ToolForbiddenError(row.tool_name)

    device = _authorize_device(session, ticket, spec, row.parameters.get("device_id", ""))

    if confirmation_id != row.correlation_id:
        raise ToolForbiddenError("confirmation mismatch")

    if row.outcome != PROPOSED:
        return _execution_record(row, device)

    if not spec.requires_confirmation:
        raise ToolValidationError("This read-only tool executes when proposed and cannot be confirmed")

    params = _validate_params(spec, row.parameters)
    result = _run(session, spec.name, device, params)

    if result.succeeded:
        if result.device_status is not None:
            device.status = result.device_status
        if result.details_updates:
            device.details = {**(device.details or {}), **result.details_updates}
            _apply_column_updates(device, result.details_updates)
        _apply_telemetry(session, ticket, device, result)
        row.outcome = SUCCEEDED
    else:
        row.outcome = FAILED
    row.message = result.message[:400]
    row.result = _result_payload(result)
    session.flush()
    _audit(
        session,
        actor_id=actor.id,
        ticket_id=ticket.id,
        event_type="tool_executed",
        details={
            "tool_name": spec.name,
            "device_ref": device.device_ref,
            "parameters": row.parameters,
            "proposal_id": row.id,
            "outcome": row.outcome,
            "message": result.message,
        },
    )
    session.commit()
    return _execution_record(row, device)


def list_proposals(session: Session, ticket_id: str, actor: AuthenticatedUser) -> list[ToolProposalRecord]:
    _authorize_ticket(session, ticket_id, actor)
    rows = (
        session.query(ToolExecution)
        .filter(ToolExecution.ticket_id == ticket_id)
        .order_by(ToolExecution.created_at)
        .all()
    )
    records = []
    for row in rows:
        spec = tool_registry.get_tool_spec(row.tool_name)
        device = session.get(NetworkDevice, row.parameters.get("device_id", ""))
        if spec is None or device is None:
            continue
        records.append(_proposal_record(row, device, spec))
    return records


def _authorize_ticket(session: Session, ticket_id: str, actor: AuthenticatedUser) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise ToolNotFoundError(ticket_id)
    require_assigned_ticket(actor.id, ticket.assigned_technician_id, actor.role)
    require_customer_scope(
        actor.id,
        actor.role,
        allowed_roles=TICKET_FULL_SCOPE_ROLES,
        ticket_assignee_id=ticket.assigned_technician_id,
        ticket_customer_id=ticket.customer_id,
        requested_customer_id=ticket.customer_id,
    )
    return ticket


def _authorize_device(
    session: Session,
    ticket: Ticket,
    spec: tool_registry.ToolSpec,
    device_id: str,
) -> NetworkDevice:
    device = session.get(NetworkDevice, device_id)
    if device is None or device.customer_id != ticket.customer_id:
        raise ToolForbiddenError("device out of scope")
    if spec.target_device_types is not None and not _device_type_allowed(spec, device.device_type):
        expected = " or ".join(spec.target_device_types)
        raise ToolForbiddenError(f"{spec.name} requires a {expected} device or managed mesh node")
    return device


def _device_type_allowed(spec: tool_registry.ToolSpec, device_type: str) -> bool:
    """Keep personal endpoints out of the control plane while allowing TM mesh nodes."""
    if spec.target_device_types is None:
        return True
    normalized = device_type.strip().lower()
    expected = {item.lower() for item in spec.target_device_types}
    if normalized in expected:
        return True
    return "router" in expected and normalized in {"mesh", "root", "satellite"}


def _validate_params(spec: tool_registry.ToolSpec, parameters: dict):
    if not isinstance(parameters, dict):
        raise ToolValidationError("parameters must be an object")
    try:
        return spec.params.model_validate(parameters)
    except ValidationError as error:
        raise ToolValidationError(_first_error(error)) from error


def _first_error(error: ValidationError) -> str:
    first = error.errors()[0]
    message = str(first.get("msg", "invalid parameters"))
    return message.removeprefix("Value error, ")


def _run(session: Session, tool_name: str, device: NetworkDevice, params) -> tool_executor.SimulationResult:
    try:
        return tool_executor.run(tool_name, device, params, _sim_context(session, device))
    except KeyError as error:
        raise ToolNotFoundError(tool_name) from error


_INFRA_TYPES = {"router", "root", "gateway", "onu", "ont", "olt"}


def _sim_context(session: Session, device: NetworkDevice) -> tool_executor.SimContext:
    """The target's clients and its router telemetry row, for tools that read the home network."""
    clients = tuple(
        session.scalars(
            select(NetworkDevice)
            .where(NetworkDevice.customer_id == device.customer_id, NetworkDevice.id != device.id)
            .order_by(NetworkDevice.device_ref)
        ).all()
    )
    clients = tuple(client for client in clients if client.device_type.strip().lower() not in _INFRA_TYPES)
    router = None
    customer = session.get(Customer, device.customer_id)
    if customer is not None:
        router = session.scalars(select(Router).where(Router.login_id == customer.customer_ref)).first()
    return tool_executor.SimContext(clients=clients, router=router)


_CLIENT_COLUMNS = {"link_type", "rssi", "tx_rate", "rx_rate"}


def _apply_telemetry(session: Session, ticket: Ticket, device: NetworkDevice, result: tool_executor.SimulationResult) -> None:
    if result.router_updates:
        router = _sim_context(session, device).router
        if router is not None:
            for column, value in result.router_updates.items():
                setattr(router, column, value)
    for client_id, updates in result.client_updates.items():
        client = session.get(NetworkDevice, client_id)
        if client is None or client.customer_id != ticket.customer_id:
            continue
        for column, value in updates.items():
            if column in _CLIENT_COLUMNS:
                setattr(client, column, value)


def _result_payload(result: tool_executor.SimulationResult) -> dict:
    return {"trace": result.trace, "data": result.data}


# Simulated radio settings mirror into the device columns the topology inspector reads.
_DETAIL_COLUMNS = {
    "channel_2g": "channel_2_4ghz",
    "channel_5g": "channel_5ghz",
    "ssid_2g": "ssid_2_4ghz",
    "ssid_5g": "ssid_5ghz",
}


def _apply_column_updates(device: NetworkDevice, updates: dict) -> None:
    for key, column in _DETAIL_COLUMNS.items():
        if key in updates:
            setattr(device, column, updates[key])


def _audit(session: Session, *, actor_id: str, ticket_id: str, event_type: str, details: dict) -> None:
    session.add(
        AuditEvent(
            actor_id=actor_id,
            ticket_id=ticket_id,
            event_type=event_type,
            details=details,
        )
    )


def _proposal_record(
    row: ToolExecution,
    device: NetworkDevice,
    spec: tool_registry.ToolSpec,
) -> ToolProposalRecord:
    return ToolProposalRecord(
        id=row.id,
        ticket_id=row.ticket_id,
        tool_name=row.tool_name,
        device_id=device.id,
        device_ref=device.device_ref,
        kind=spec.kind,
        requires_confirmation=spec.requires_confirmation,
        parameters=row.parameters,
        status=row.outcome,
        summary=_summary(spec, row.parameters, device),
        correlation_id=row.correlation_id,
        created_at=row.created_at or datetime.now(UTC),
        result=row.result,
    )


def _execution_record(row: ToolExecution, device: NetworkDevice) -> ToolExecutionRecord:
    message = row.message
    if message is None and row.outcome == PROPOSED:
        message = "Awaiting confirmation."
    return ToolExecutionRecord(
        id=row.id,
        ticket_id=row.ticket_id,
        tool_name=row.tool_name,
        device_id=device.id,
        device_ref=device.device_ref,
        status=row.outcome,
        message=message or "",
        correlation_id=row.correlation_id,
        executed_at=row.created_at or datetime.now(UTC),
        result=row.result,
    )


def _summary(spec: tool_registry.ToolSpec, parameters: dict, device: NetworkDevice) -> str:
    extras = {
        key: value
        for key, value in parameters.items()
        if key != "device_id" and value not in (None, {}, [])
    }
    detail = ""
    if extras:
        rendered = ", ".join(f"{key}={_render_value(value)}" for key, value in sorted(extras.items()))
        detail = f" ({rendered})"
    return f"{spec.title}: {spec.description}{detail} on {device.device_ref}"


def _render_value(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={value[key]}" for key in sorted(value))
    return str(value)
