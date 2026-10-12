from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.ports import ChatCompletionProvider, EmbeddingProvider
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.config import Settings, get_settings
from app.db.session import get_session
from app.domain.customer_chat_schemas import CustomerChatRequest, CustomerVisibleHistory, CustomerVisibleResponse, CustomerVisibleTurn
from app.domain.diagnostic_schemas import CustomerDiagnosticsRead
from app.integrations.embeddings import build_embedding_provider
from app.integrations.model_provider import build_chat_provider
from app.services import customer_chat
from app.services.customer_diagnostics import CustomerAccountNotFoundError, get_my_diagnostics
from app.domain.appointment_schemas import AppointmentAvailability, AppointmentBookingRequest, AppointmentRead
from app.services import customer_appointments

router = APIRouter(prefix="/portal", tags=["customer portal"])


def get_portal_embedder() -> EmbeddingProvider:
    return build_embedding_provider(get_settings())


def get_portal_chat_provider() -> ChatCompletionProvider:
    settings = get_settings()
    return build_chat_provider(settings.model_copy(update={"model_provider": settings.customer_chat_provider}),
        timeout_seconds=15.0 if settings.customer_chat_mode == "agent" else 60.0,
        max_output_tokens=1024 if settings.customer_chat_mode == "agent" else None)


@router.post("/me/chat/messages", response_model=CustomerVisibleResponse)
def customer_chat_message(
    payload: CustomerChatRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    embedder: EmbeddingProvider = Depends(get_portal_embedder),
    provider: ChatCompletionProvider = Depends(get_portal_chat_provider),
):
    try:
        response = customer_chat.answer_customer(session, user, payload, settings=settings, embedder=embedder, provider=provider)
        return customer_chat.visible_response(response)
    except CustomerAccountNotFoundError as error:
        raise HTTPException(status_code=403, detail="No customer account is linked to this login") from error
    except customer_chat.ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error
    except customer_chat.CustomerChatConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except customer_chat.InsecureCustomerGatewayError as error:
        raise HTTPException(status_code=403, detail="Real customer chat requires model gateway TLS verification") from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="A message was submitted concurrently. Retry with the same request ID.") from error


@router.get("/me/chat/conversations/{conversation_id}", response_model=CustomerVisibleHistory)
def customer_chat_history(
    conversation_id: UUID,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        history = customer_chat.get_history(session, user, str(conversation_id))
        return CustomerVisibleHistory(conversation_id=history.conversation_id, turns=[
            CustomerVisibleTurn(message=turn.message, response=customer_chat.visible_response(turn.response))
            for turn in history.turns
        ])
    except CustomerAccountNotFoundError as error:
        raise HTTPException(status_code=403, detail="No customer account is linked to this login") from error
    except customer_chat.ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error


@router.get("/me/diagnostics", response_model=CustomerDiagnosticsRead)
def my_diagnostics(
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> CustomerDiagnosticsRead:
    try:
        return get_my_diagnostics(session, user)
    except CustomerAccountNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No customer account is linked to this login",
        ) from error


def _appointment_call(session, function, *args):
    try:
        return function(session, *args)
    except customer_appointments.AppointmentNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail="Ticket or appointment not found") from error
    except customer_appointments.AppointmentConflictError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/me/reports/{ticket_id}/appointment-slots", response_model=AppointmentAvailability)
def appointment_slots(ticket_id: UUID, session: Session = Depends(get_session), user: AuthenticatedUser = Depends(get_current_user)):
    return _appointment_call(session, customer_appointments.availability, user, str(ticket_id))


@router.post("/me/reports/{ticket_id}/appointments", response_model=AppointmentRead)
def book_visit(ticket_id: UUID, payload: AppointmentBookingRequest, session: Session = Depends(get_session), user: AuthenticatedUser = Depends(get_current_user)):
    return _appointment_call(session, customer_appointments.book_appointment, user, str(ticket_id), payload)


@router.delete("/me/reports/{ticket_id}/appointments/{appointment_id}", response_model=AppointmentRead)
def cancel_visit(ticket_id: UUID, appointment_id: UUID, session: Session = Depends(get_session), user: AuthenticatedUser = Depends(get_current_user)):
    return _appointment_call(session, customer_appointments.cancel_appointment, user, str(ticket_id), str(appointment_id))
