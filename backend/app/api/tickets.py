from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.session import get_session
from app.domain.models import Service
from app.domain.schemas import (
    AssignedTicketRead,
    CredentialRevealRead,
    CustomerRead,
    CustomerSummaryRead,
    DeviceRead,
    EntityFactRead,
    ServiceCredentialRevealRead,
    ServiceRead,
    RouterRead,
    TicketDetailRead,
    TicketFactsRead,
    TicketRead,
    TopologyEdgeRead,
    TopologyNodeRead,
    TopologyPathRead,
    find_credential,
)
from app.services import ticket_queries
from app.services.ticket_queries import (
    CredentialUnavailableError,
    TicketNotFoundError,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("/mine", response_model=list[AssignedTicketRead])
def list_my_tickets(
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[AssignedTicketRead]:
    records = ticket_queries.list_assigned_tickets(session, user)
    return [
        AssignedTicketRead(
            id=record.id,
            source_event_id=record.source_event_id,
            customer_id=record.customer_id,
            service_id=record.service_id,
            assigned_technician_id=record.assigned_technician_id,
            severity=record.severity,
            status=record.status,
            summary=record.summary,
            customer_ref=record.customer_ref,
            customer_name=record.customer_name,
            service_type=record.service_type,
            service_ref=record.service_ref,
            appointment=record.appointment,
            tm_ticket_no=record.tm_ticket_no,
            login_id=record.login_id,
        )
        for record in records
    ]


@router.get("/{ticket_id}", response_model=TicketDetailRead)
def get_ticket(
    ticket_id: str,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> TicketDetailRead:
    try:
        record = ticket_queries.get_ticket_detail(session, ticket_id, user)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error

    return TicketDetailRead(
        ticket=TicketRead.model_validate(record.ticket),
        assigned_technician_name=record.assigned_technician_name,
        customer=CustomerRead.model_validate(record.customer),
        services=[_service_read(service) for service in record.services],
        devices=[_device_read(device) for device in record.devices],
        routers=[RouterRead.model_validate(router) for router in record.routers],
        customer_summary=CustomerSummaryRead.model_validate(record.customer_summary) if record.customer_summary else None,
        appointment=record.appointment,
    )


@router.get("/{ticket_id}/facts", response_model=TicketFactsRead)
def get_ticket_facts(
    ticket_id: str,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> TicketFactsRead:
    try:
        facts = ticket_queries.list_ticket_facts(session, ticket_id, user)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error

    return TicketFactsRead(
        ticket_id=ticket_id,
        facts=[
            EntityFactRead(
                entity_type=fact.entity_type,
                entity_id=fact.entity_id,
                group_key=fact.group_key,
                field_key=fact.field_key,
                label=fact.label,
                value_text=fact.value_text,
                value_number=fact.value_number,
                is_sensitive=fact.is_sensitive,
            )
            for fact in facts
        ],
    )


@router.get("/{ticket_id}/topology", response_model=TopologyPathRead)
def get_ticket_topology(
    ticket_id: str,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> TopologyPathRead:
    try:
        record = ticket_queries.get_ticket_topology(session, ticket_id, user)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error

    return TopologyPathRead(
        ticket_id=record.ticket_id,
        service_id=record.service_id,
        service_ref=record.service_ref,
        nodes=[
            TopologyNodeRead(
                device_id=node.device_id,
                device_ref=node.device_ref,
                device_type=node.device_type,
                name=node.name,
                status=node.status,
                service_id=node.service_id,
                service_ref=node.service_ref,
            )
            for node in record.nodes
        ],
        edges=[
            TopologyEdgeRead(
                source_device_id=edge.source_device_id,
                target_device_id=edge.target_device_id,
                service_id=edge.service_id,
                service_ref=edge.service_ref,
            )
            for edge in record.edges
        ],
    )


@router.get("/{ticket_id}/devices/{device_id}/credential", response_model=CredentialRevealRead)
def reveal_device_credential(
    ticket_id: str,
    device_id: str,
    response: Response,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> CredentialRevealRead:
    try:
        record = ticket_queries.reveal_device_credential(session, ticket_id, device_id, user)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error
    except CredentialUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No credential is available for this device",
        ) from error

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return CredentialRevealRead(
        device_id=record.device_id,
        device_ref=record.device_ref,
        credential_type=record.credential_type,
        credential=record.credential,
    )


@router.get(
    "/{ticket_id}/services/{service_id}/credential",
    response_model=ServiceCredentialRevealRead,
)
def reveal_service_credential(
    ticket_id: str,
    service_id: str,
    response: Response,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ServiceCredentialRevealRead:
    try:
        record = ticket_queries.reveal_service_credential(session, ticket_id, service_id, user)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error
    except CredentialUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No credential is available for this service",
        ) from error

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return ServiceCredentialRevealRead(
        service_id=record.service_id,
        service_ref=record.service_ref,
        credential_type=record.credential_type,
        credential=record.credential,
    )


def _device_read(device: ticket_queries.DeviceRecord) -> DeviceRead:
    read = DeviceRead.model_validate(device.source)
    read.credential_available = device.credential_available
    return read


def _service_read(service: Service) -> ServiceRead:
    return ServiceRead(
        id=service.id,
        service_type=service.service_type,
        service_ref=service.service_ref,
        status=service.status,
        details=service.details,
        credential_available=find_credential(service.details) is not None,
    )
