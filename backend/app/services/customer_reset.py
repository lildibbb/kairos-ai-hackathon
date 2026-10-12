"""Remove customer-portal demo records without touching seeded inventory."""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser
from app.domain.models import (
    AssistantMessage, AssistantSession, AuditEvent, Customer, CustomerAccount,
    CustomerAppointment, CustomerChatConversation, CustomerChatTurn,
    CustomerRouterAction, CustomerTroubleTicket, EntityFact, EntityFactSheet,
    NetworkEvent, Ticket, ToolExecution,
)


class CustomerResetNotAllowedError(Exception):
    pass


def reset_customer_demo_data(session: Session, actor: AuthenticatedUser) -> int:
    """Delete reports and conversations created by this demo customer login."""
    link = session.get(CustomerAccount, actor.id)
    customer = session.get(Customer, link.customer_id) if link else None
    if customer is None or not customer.is_demo:
        raise CustomerResetNotAllowedError()

    conversation_ids = list(session.scalars(select(CustomerChatConversation.id).where(
        CustomerChatConversation.user_id == actor.id,
        CustomerChatConversation.customer_id == customer.id,
    )))
    if not conversation_ids:
        return 0

    report_rows = list(session.execute(select(CustomerTroubleTicket.id, CustomerTroubleTicket.ticket_id).where(
        CustomerTroubleTicket.conversation_id.in_(conversation_ids),
    )))
    report_ids = [row[0] for row in report_rows]
    ticket_ids = [row[1] for row in report_rows if row[1]]
    event_ids = list(session.scalars(select(NetworkEvent.id).where(
        NetworkEvent.source_event_id.in_([f"CUSTOMER-REPORT-{report_id}" for report_id in report_ids]),
    ))) if report_ids else []

    if ticket_ids:
        session.execute(update(CustomerTroubleTicket).where(CustomerTroubleTicket.id.in_(report_ids)).values(ticket_id=None))
        session.execute(delete(AssistantMessage).where(AssistantMessage.session_id.in_(
            select(AssistantSession.id).where(AssistantSession.ticket_id.in_(ticket_ids)),
        )))
        session.execute(delete(AssistantSession).where(AssistantSession.ticket_id.in_(ticket_ids)))
        session.execute(delete(ToolExecution).where(ToolExecution.ticket_id.in_(ticket_ids)))
        session.execute(delete(EntityFact).where(EntityFact.entity_type == "ticket", EntityFact.entity_id.in_(ticket_ids)))
        session.execute(delete(EntityFactSheet).where(EntityFactSheet.entity_type == "ticket", EntityFactSheet.entity_id.in_(ticket_ids)))
        session.execute(delete(AuditEvent).where(AuditEvent.ticket_id.in_(ticket_ids)))
        session.execute(delete(Ticket).where(Ticket.id.in_(ticket_ids)))
    if event_ids:
        session.execute(delete(NetworkEvent).where(NetworkEvent.id.in_(event_ids)))

    session.execute(delete(CustomerAppointment).where(CustomerAppointment.ticket_id.in_(report_ids)))
    report_audits = list(session.scalars(select(AuditEvent).where(
        AuditEvent.actor_id == actor.id,
        AuditEvent.event_type == "customer_report_created",
    )))
    for audit in report_audits:
        if audit.details.get("report_id") in report_ids:
            session.delete(audit)
    session.execute(delete(CustomerTroubleTicket).where(CustomerTroubleTicket.id.in_(report_ids)))
    session.execute(delete(CustomerRouterAction).where(CustomerRouterAction.conversation_id.in_(conversation_ids)))
    session.execute(delete(CustomerChatTurn).where(CustomerChatTurn.conversation_id.in_(conversation_ids)))
    session.execute(delete(CustomerChatConversation).where(CustomerChatConversation.id.in_(conversation_ids)))
    session.flush()
    return len(report_ids)
