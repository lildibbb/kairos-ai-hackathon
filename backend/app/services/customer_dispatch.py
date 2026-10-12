"""Deterministic local routing. No external workforce system or equipment calls."""

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    AuditEvent, Customer, CustomerDispatchArea, CustomerTroubleTicket, DispatchArea,
    Role, TechnicianDispatchArea, User,
)


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
    session.add(AuditEvent(actor_id=actor_id, event_type="customer_report_created", details={
        "report_id": report.id, "reference": report.reference, "reason": reason,
        "area_id": report.area_id, "assigned_technician_id": report.assigned_technician_id,
        "status": report.status, "is_demo": report.is_demo,
    }))
    return report
