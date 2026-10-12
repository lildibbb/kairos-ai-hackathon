"""Small read-only checker for local customer-chat testing, not the staff workspace."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, require_roles
from app.db.session import get_session
from app.domain.appointment_schemas import AppointmentRead
from app.services.customer_appointments import active_appointment, appointment_read
from app.domain.customer_chat_schemas import CustomerChatHistory, CustomerChatHistoryTurn, CustomerChatResponse
from app.domain.models import (
    Customer, CustomerChatConversation, CustomerChatTurn, CustomerTroubleTicket, DispatchArea, User,
)

router = APIRouter(prefix="/admin/customer-reports", tags=["customer report checker"])
checker_user = require_roles("operator", "supervisor")


class ReportCheck(BaseModel):
    reference: str
    status: str
    area: str | None
    technician: str | None
    reason: str
    appointment: AppointmentRead | None = None


class ConversationCheck(BaseModel):
    id: str
    customer_ref: str
    customer_name: str
    created_at: datetime
    turn_count: int
    status: str
    is_demo: bool
    report: ReportCheck | None


@router.get("", response_model=list[ConversationCheck])
def list_reports(session: Session = Depends(get_session), user: AuthenticatedUser = Depends(checker_user)):
    latest = select(func.max(CustomerChatTurn.position)).where(
        CustomerChatTurn.conversation_id == CustomerChatConversation.id,
    ).correlate(CustomerChatConversation).scalar_subquery()
    rows = session.execute(select(CustomerChatConversation, Customer, CustomerChatTurn).join(
        Customer, Customer.id == CustomerChatConversation.customer_id,
    ).join(CustomerChatTurn, (CustomerChatTurn.conversation_id == CustomerChatConversation.id) &
           (CustomerChatTurn.position == latest)).order_by(CustomerChatConversation.created_at.desc()).limit(100)).all()
    references = [turn.response.get("report", {}).get("reference") for _, _, turn in rows if turn.response.get("report")]
    reports = session.execute(select(CustomerTroubleTicket, DispatchArea.name, User.display_name).outerjoin(
        DispatchArea, DispatchArea.id == CustomerTroubleTicket.area_id,
    ).outerjoin(User, User.id == CustomerTroubleTicket.assigned_technician_id).where(
        CustomerTroubleTicket.reference.in_(references),
    )).all()
    by_reference = {}
    for report, area, technician in reports:
        active = active_appointment(session, report.id)
        by_reference[report.reference] = ReportCheck(reference=report.reference, status=report.status,
            area=area, technician=technician, reason=report.reason,
            appointment=appointment_read(session, active) if active else None)
    return [ConversationCheck(id=conversation.id, customer_ref=customer.customer_ref,
        customer_name=customer.name, created_at=conversation.created_at, turn_count=turn.position,
        status=turn.response["status"], is_demo=customer.is_demo,
        report=by_reference.get((turn.response.get("report") or {}).get("reference")))
        for conversation, customer, turn in rows]


@router.get("/{conversation_id}", response_model=CustomerChatHistory)
def inspect_conversation(conversation_id: UUID, session: Session = Depends(get_session),
                         user: AuthenticatedUser = Depends(checker_user)):
    conversation = session.get(CustomerChatConversation, str(conversation_id))
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    turns = session.scalars(select(CustomerChatTurn).where(
        CustomerChatTurn.conversation_id == conversation.id,
    ).order_by(CustomerChatTurn.position).limit(30))
    return CustomerChatHistory(conversation_id=conversation.id, turns=[
        CustomerChatHistoryTurn(message=turn.message, response=CustomerChatResponse.model_validate(turn.response))
        for turn in turns
    ])
