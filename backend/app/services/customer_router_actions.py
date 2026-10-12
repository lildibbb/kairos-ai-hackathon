"""Confirmation-backed, fictional-household-only router simulator. No hardware I/O."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.domain.customer_chat_schemas import AnswerChoice, CustomerRouterActionRead, FollowUpQuestion
from app.domain.models import (
    AuditEvent, Customer, CustomerAccount, CustomerChatConversation, CustomerRouterAction,
    CustomerRouterState, NetworkDevice, Service, User,
)

# Fictional showcase profile, not authoritative Unifi provisioning values.
SIMULATED_VLANS = {"HSI": 500, "IPTV": 600, "VoBB": 400}


class RouterActionError(ValueError):
    pass


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _scope(session, actor, settings):
    if not settings.customer_router_simulation_enabled or settings.app_environment not in ("development", "test"):
        raise RouterActionError("Router simulation is not enabled.")
    user = session.get(User, actor.id)
    link = session.get(CustomerAccount, actor.id)
    customer = session.scalar(select(Customer).where(Customer.id == link.customer_id).with_for_update()) if link else None
    if actor.role != "customer" or not user or not user.is_active or not user.is_demo or not customer or not customer.is_demo:
        raise RouterActionError("Router simulation requires a fictional customer account.")
    routers = list(session.scalars(select(NetworkDevice).where(
        NetworkDevice.customer_id == customer.id, NetworkDevice.device_type == "router",
    ).with_for_update()))
    if len(routers) != 1 or not (routers[0].details or {}).get("is_synthetic"):
        raise RouterActionError("Exactly one synthetic household router is required.")
    return customer, routers[0]


def capability(session, actor, settings):
    try:
        customer, device = _scope(session, actor, settings)
    except RouterActionError:
        return {"enabled": False, "services": []}
    services = list(session.scalars(select(Service.service_type).where(
        Service.customer_id == customer.id, Service.status == "active", Service.service_type.in_(SIMULATED_VLANS),
    )))
    state = session.get(CustomerRouterState, device.id)
    vlans = state.service_vlans if state else {key: SIMULATED_VLANS[key] for key in services}
    return {"enabled": True, "services": sorted(services), "simulation": True,
            "reboot_count": state.reboot_count if state else 0,
            "service_vlans": vlans, "approved_service_vlans": {key: SIMULATED_VLANS[key] for key in services},
            "mismatched_services": [key for key in services if vlans.get(key) != SIMULATED_VLANS[key]]}


def read_action(row, *, now=None):
    status = "expired" if row.status == "pending" and utc(row.expires_at) <= utc(now or datetime.now(UTC)) else row.status
    label = "Restart router" if row.kind == "reboot" else f"Restore {row.service_type} VLAN configuration"
    return CustomerRouterActionRead(id=row.id, kind=row.kind, label=label, status=status, expires_at=utc(row.expires_at))


def owned_action(session, actor, conversation_id, action_id):
    link = session.get(CustomerAccount, actor.id)
    row = session.scalar(select(CustomerRouterAction).where(
        CustomerRouterAction.id == str(action_id), CustomerRouterAction.user_id == actor.id,
        CustomerRouterAction.conversation_id == conversation_id,
        CustomerRouterAction.customer_id == (link.customer_id if link else None),
    ).with_for_update())
    if not row:
        raise RouterActionError("This router action is unavailable in this conversation.")
    return row


def _audit(session, actor, row, event, **details):
    session.add(AuditEvent(actor_id=actor.id, event_type=event, details={
        "action_id": row.id, "conversation_id": row.conversation_id,
        "kind": row.kind, "simulation": True, **details,
    }))


def propose(session, actor, settings, conversation_id, request_id, kind, *, service_type="HSI", now):
    customer, device = _scope(session, actor, settings)
    conversation = session.get(CustomerChatConversation, conversation_id)
    if not conversation or conversation.user_id != actor.id or conversation.customer_id != customer.id:
        raise RouterActionError("The router action does not belong to this conversation.")
    if kind not in ("reboot", "restore_vlan"):
        raise RouterActionError("Unsupported router action.")
    if kind == "restore_vlan" and service_type not in capability(session, actor, settings)["services"]:
        raise RouterActionError("That service cannot be restored for this household.")
    pending = session.scalar(select(CustomerRouterAction).where(
        CustomerRouterAction.device_id == device.id, CustomerRouterAction.status == "pending",
        CustomerRouterAction.expires_at > now,
    ))
    if pending:
        raise RouterActionError("Finish or cancel the pending router action before requesting another.")
    completed = session.scalar(select(CustomerRouterAction).where(
        CustomerRouterAction.device_id == device.id, CustomerRouterAction.status == "succeeded",
        CustomerRouterAction.kind == kind, CustomerRouterAction.completed_at > now - timedelta(seconds=30),
    ))
    if completed:
        raise RouterActionError("Wait briefly before repeating the same router action.")
    row = CustomerRouterAction(conversation_id=conversation_id, customer_id=customer.id, user_id=actor.id,
        device_id=device.id, request_id=str(request_id), kind=kind,
        service_type=service_type if kind == "restore_vlan" else None,
        status="pending", details={"simulation": True}, expires_at=now + timedelta(minutes=10))
    session.add(row)
    session.flush()
    _audit(session, actor, row, "customer_router_action_proposed")
    return row


def confirm(session, actor, settings, conversation_id, action_id, *, cancel=False, now):
    _, device = _scope(session, actor, settings)
    row = owned_action(session, actor, conversation_id, action_id)
    if row.device_id != device.id:
        raise RouterActionError("The router target has changed. Start a new check.")
    if row.status != "pending":
        return row
    if read_action(row, now=now).status == "expired":
        raise RouterActionError("This confirmation has expired. Request the action again.")
    if cancel:
        row.status = "cancelled"
        row.completed_at = now
        _audit(session, actor, row, "customer_router_action_cancelled")
        session.flush()
        return row
    services = capability(session, actor, settings)["services"]
    if row.kind == "restore_vlan" and row.service_type not in services:
        raise RouterActionError("The service is no longer eligible for restoration.")
    state = session.get(CustomerRouterState, device.id)
    if not state:
        state = CustomerRouterState(device_id=device.id, reboot_count=0,
            service_vlans={key: SIMULATED_VLANS[key] for key in services})
        session.add(state)
    before = {"reboot_count": state.reboot_count, "service_vlans": dict(state.service_vlans)}
    if row.kind == "reboot":
        state.reboot_count += 1
    else:
        state.service_vlans = {**state.service_vlans, row.service_type: SIMULATED_VLANS[row.service_type]}
    state.last_action_at = now
    row.status = "succeeded"
    row.completed_at = now
    row.details = {"simulation": True, "before": before,
        "after": {"reboot_count": state.reboot_count, "service_vlans": dict(state.service_vlans)},
        "verification": "simulated_execution_only_customer_improvement_not_verified"}
    _audit(session, actor, row, "customer_router_action_executed", **row.details)
    session.flush()
    return row


def confirmation_question():
    return FollowUpQuestion(id="router_action_confirmation",
        question="Would you like to proceed with this simulated router action?",
        choices=[AnswerChoice(value="confirm_router_action", label="Confirm action"),
                 AnswerChoice(value="cancel_router_action", label="Cancel action")])


def improvement_question():
    return FollowUpQuestion(id="router_action_check", question="Please try the affected service again. Has it improved?",
        choices=[AnswerChoice(value="resolved", label="It's working now"),
                 AnswerChoice(value="still_not_working", label="Still not working"),
                 AnswerChoice(value="request_technician", label="Request a technician")])
