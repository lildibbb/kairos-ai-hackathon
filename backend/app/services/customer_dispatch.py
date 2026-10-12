"""Deterministic local routing. No external workforce system or equipment calls."""

from datetime import UTC, datetime
from hashlib import sha1
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    AuditEvent, Customer, CustomerChatConversation, CustomerDispatchArea, CustomerTroubleTicket, DispatchArea,
    NetworkDevice, NetworkEvent, Role, Service, TechnicianDispatchArea, Ticket, User,
)
from app.services.entity_facts import sync_ticket_facts

# A chatbot report is mirrored into the staff ticket table only when routing
# assigned a technician. The synthetic event keeps the field-operations ticket
# self-describing without pretending a real network alarm occurred.
_EVENT_TYPE_BY_INTENT = {
    "no_internet": "CUSTOMER_NO_INTERNET",
    "slow_internet": "CUSTOMER_SLOW_INTERNET",
    "disconnecting": "CUSTOMER_DISCONNECTING",
    "voice": "CUSTOMER_VOICE",
    "iptv": "CUSTOMER_IPTV",
    "other": "CUSTOMER_REPORT",
}
_SEVERITY_BY_INTENT = {
    "no_internet": "high",
    "disconnecting": "high",
    "voice": "high",
}


def create_report(session: Session, *, customer_id: str, conversation_id: str,
                  actor_id: str, intent: str, reason: str) -> CustomerTroubleTicket:
    # Serialize household reports, including requests from different conversations/logins.
    customer = session.scalar(select(Customer).where(Customer.id == customer_id).with_for_update())
    existing = session.scalar(select(CustomerTroubleTicket).where(
        CustomerTroubleTicket.customer_id == customer_id,
        CustomerTroubleTicket.intent == intent,
        CustomerTroubleTicket.status.in_(("assigned", "queued")),
    ).order_by(CustomerTroubleTicket.created_at))
    if existing:
        if existing.status == "assigned" and existing.assigned_technician_id:
            sync_report_ticket(session, report=existing,
                technician=session.get(User, existing.assigned_technician_id), actor_id=actor_id)
        return existing
    mapping = session.get(CustomerDispatchArea, customer_id)
    area = session.get(DispatchArea, mapping.area_id) if mapping else None
    if area and (not area.is_active or area.is_demo != customer.is_demo):
        area = None
    technician = None
    if area:
        # Lock the area's eligible technicians in a stable order before load comparison.
        candidates = list(session.scalars(select(User).join(Role).join(
            TechnicianDispatchArea, TechnicianDispatchArea.user_id == User.id,
        ).where(
            Role.name == "technician", User.is_active.is_(True), User.is_demo == customer.is_demo,
            TechnicianDispatchArea.area_id == area.id, TechnicianDispatchArea.is_available.is_(True),
        ).order_by(User.id).with_for_update(of=User)))
        if candidates:
            def load(user):
                return session.scalar(select(func.count()).select_from(CustomerTroubleTicket).where(
                    CustomerTroubleTicket.assigned_technician_id == user.id,
                    CustomerTroubleTicket.status == "assigned",
                )), user.id
            technician = min(candidates, key=load)
    report = CustomerTroubleTicket(
        reference=f"{'DEMO-' if customer.is_demo else ''}TT-{uuid4().hex[:16].upper()}",
        conversation_id=conversation_id, customer_id=customer_id, intent=intent,
        summary=f"Customer reports {intent.replace('_', ' ')}; technician review requested.",
        reason=reason, area_id=area.id if area else None,
        assigned_technician_id=technician.id if technician else None,
        status="assigned" if technician else "queued", is_demo=customer.is_demo,
    )
    session.add(report)
    session.flush()
    field_ops_ticket = sync_report_ticket(
        session, report=report, technician=technician, actor_id=actor_id,
    )
    session.add(AuditEvent(actor_id=actor_id, ticket_id=field_ops_ticket.id if field_ops_ticket else None,
        event_type="customer_report_created", details={
        "report_id": report.id, "reference": report.reference, "reason": reason,
        "area_id": report.area_id, "assigned_technician_id": report.assigned_technician_id,
        "status": report.status, "is_demo": report.is_demo,
        "field_ops_ticket_id": field_ops_ticket.id if field_ops_ticket else None,
        "field_ops_ticket_no": field_ops_ticket.tm_ticket_no if field_ops_ticket else None,
    }))
    return report


def sync_report_ticket(session: Session, *, report: CustomerTroubleTicket,
                       technician: User | None, actor_id: str) -> Ticket | None:
    """Create or refresh the staff ticket that mirrors an assigned customer report.

    Returns ``None`` when the report is still queued (no technician). When the
    report already has a staff ticket, the technician is written through so a
    rescheduled appointment stays in step with the field-operations ticket.
    """
    if technician is None:
        return None
    if report.ticket_id:
        existing = session.get(Ticket, report.ticket_id)
        if existing is not None:
            existing.assigned_technician_id = technician.id
            existing.staff_code = technician.staff_code
            sync_ticket_facts(session, existing)
            return existing
    return _mirror_to_field_ops_ticket(session, report=report, technician=technician, actor_id=actor_id)


def backfill_report_tickets(session: Session) -> dict[str, int]:
    """Link historical assigned reports, using the same household lock as chat."""
    counts = {"linked": 0, "skipped": 0}
    missing = (CustomerTroubleTicket.ticket_id.is_(None),
               CustomerTroubleTicket.status == "assigned",
               CustomerTroubleTicket.assigned_technician_id.is_not(None))
    customer_ids = list(session.scalars(select(CustomerTroubleTicket.customer_id)
        .where(*missing).distinct().order_by(CustomerTroubleTicket.customer_id)))
    for customer_id in customer_ids:
        session.scalar(select(Customer).where(Customer.id == customer_id).with_for_update())
        reports = session.scalars(select(CustomerTroubleTicket)
            .where(CustomerTroubleTicket.customer_id == customer_id, *missing)
            .order_by(CustomerTroubleTicket.id).with_for_update())
        for report in reports:
            conversation = session.get(CustomerChatConversation, report.conversation_id)
            ticket = sync_report_ticket(session, report=report,
                technician=session.get(User, report.assigned_technician_id), actor_id=conversation.user_id)
            counts["linked" if ticket else "skipped"] += 1
    session.flush()
    return counts


def _mirror_to_field_ops_ticket(session: Session, *, report: CustomerTroubleTicket,
                                technician: User | None, actor_id: str) -> Ticket | None:
    """Insert a staff-facing ticket for an assigned chatbot report.

    Returns ``None`` when the report is queued (no technician) or the household
    has no device to attach a synthetic event to; the customer report still
    exists in that case.
    """
    if technician is None:
        return None
    customer = session.get(Customer, report.customer_id)
    if customer is None:
        return None
    source_event_id = f"CUSTOMER-REPORT-{report.id}"
    prior = session.scalar(select(Ticket).join(NetworkEvent, NetworkEvent.id == Ticket.source_event_id)
        .where(NetworkEvent.source_event_id == source_event_id))
    if prior is not None:
        report.ticket_id = prior.id
        prior.assigned_technician_id = technician.id
        prior.staff_code = technician.staff_code
        sync_ticket_facts(session, prior)
        return prior
    device = session.scalar(select(NetworkDevice).where(
        NetworkDevice.customer_id == customer.id, NetworkDevice.device_type == "router",
    ).order_by(NetworkDevice.id))
    if device is None:
        device = session.scalar(select(NetworkDevice).where(
            NetworkDevice.customer_id == customer.id,
        ).order_by(NetworkDevice.id))
    if device is None:
        return None
    service = session.scalar(select(Service).where(
        Service.customer_id == customer.id, Service.service_type == "HSI",
    ).order_by(Service.id))
    now = datetime.now(UTC)
    event = NetworkEvent(
        source_event_id=source_event_id,
        event_type=_EVENT_TYPE_BY_INTENT.get(report.intent, "CUSTOMER_REPORT"),
        device_id=device.id, service_id=service.id if service else None,
        payload={"origin": "customer_portal", "report_reference": report.reference,
                 "intent": report.intent, "reason": report.reason},
        processed_at=now,
    )
    session.add(event)
    session.flush()
    actor = session.get(User, actor_id)
    ticket = Ticket(
        source_event_id=event.id, customer_id=customer.id, service_id=event.service_id,
        assigned_technician_id=technician.id,
        severity=_SEVERITY_BY_INTENT.get(report.intent, "medium"), status="open",
        summary=report.summary,
        tm_ticket_no=f"INC-{now:%Y%m%d}-{sha1(report.id.encode()).hexdigest()[:4].upper()}",
        ctt_activity_id=f"ACT-{device.device_ref}", login_id=actor.email if actor else None,
        ticket_category=report.intent, ticket_created_at=now, staff_code=technician.staff_code,
    )
    session.add(ticket)
    session.flush()
    report.ticket_id = ticket.id
    sync_ticket_facts(session, ticket)
    session.add(AuditEvent(actor_id=actor_id, ticket_id=ticket.id,
        event_type="customer_report_linked", details={
            "report_id": report.id, "reference": report.reference,
            "assigned_technician_id": technician.id,
        }))
    return ticket
