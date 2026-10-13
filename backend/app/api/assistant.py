import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.ports import ChatCompletionProvider, EmbeddingProvider
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.tokens import decode_access_token
from app.config import get_settings
from app.db.session import get_session
from app.domain.assistant_schemas import (
    AssistantAnswerRead,
    AssistantCitationRead,
    AssistantMessageRequest,
    NextBestActionRead,
    AssistantSummaryRead,
)
from app.integrations.embeddings import build_embedding_provider
from app.integrations.model_provider import build_chat_provider
from app.services import assistant
from app.services.assistant import AssistantAnswerRecord, AssistantFormatError
from app.services.ticket_queries import TicketNotFoundError
from app.domain.models import Role, User

router = APIRouter(prefix="/tickets", tags=["assistant"])


@router.websocket("/{ticket_id}/assistant/stream")
async def stream_assistant_message(
    websocket: WebSocket,
    ticket_id: str,
    session: Session = Depends(get_session),
) -> None:
    """Send ticket-scoped assistant progress and a validated final answer as JSON frames."""
    await websocket.accept()
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return
    try:
        claims = decode_access_token(token)
    except ValueError:
        await websocket.close(code=4401, reason="Authentication required")
        return
    user_row = session.scalar(
        select(User).where(User.id == claims["sub"], User.is_active.is_(True))
    )
    role = session.get(Role, user_row.role_id) if user_row else None
    if user_row is None or role is None or role.name != claims["role"]:
        await websocket.close(code=4401, reason="Authentication required")
        return
    actor = AuthenticatedUser(id=user_row.id, email=user_row.email, role=role.name)
    await websocket.send_json({"type": "ready"})
    try:
        while True:
            payload = await websocket.receive_json()
            question = payload.get("question") if isinstance(payload, dict) else None
            if not isinstance(question, str) or not question.strip() or len(question) > 1000:
                await websocket.send_json({"type": "error", "message": "Question must be 1 to 1000 characters."})
                continue
            await websocket.send_json({"type": "retrieval_started"})
            try:
                record = await _answer_with_progress(websocket, session, ticket_id, actor, question)
            except TicketNotFoundError:
                await websocket.send_json({"type": "error", "message": "Ticket not found or unavailable."})
                await websocket.close(code=4404)
                return
            except AssistantFormatError:
                await websocket.send_json({"type": "error", "message": "The assistant returned an unreadable answer. Retry the question."})
                continue
            except (RuntimeError, httpx.HTTPError):
                await websocket.send_json({"type": "error", "message": "The model service is unavailable. Check provider settings and connectivity, then retry."})
                continue
            await websocket.send_json({"type": "answer", "data": _to_read(record).model_dump()})
            await websocket.send_json({"type": "complete", "session_id": record.session_id})
    except WebSocketDisconnect:
        return


async def _answer_with_progress(
    websocket: WebSocket,
    session: Session,
    ticket_id: str,
    actor: AuthenticatedUser,
    question: str,
) -> AssistantAnswerRecord:
    """Run the blocking answer pipeline off the event loop and stream its step events."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    def progress(event: dict[str, str]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "step", **event})

    task = loop.run_in_executor(
        None,
        lambda: assistant.answer_ticket_question(
            session,
            ticket_id,
            actor,
            question,
            embedder=build_embedding_provider(get_settings()),
            provider=build_chat_provider(get_settings()),
            on_progress=progress,
        ),
    )
    while True:
        getter = asyncio.ensure_future(queue.get())
        done, _ = await asyncio.wait({task, getter}, return_when=asyncio.FIRST_COMPLETED)
        if getter in done:
            await websocket.send_json(getter.result())
            continue
        getter.cancel()
        break
    while not queue.empty():
        await websocket.send_json(queue.get_nowait())
    return task.result()


def get_embedding_provider() -> EmbeddingProvider:
    return build_embedding_provider(get_settings())


def get_chat_provider() -> ChatCompletionProvider:
    return build_chat_provider(get_settings())


@router.post("/{ticket_id}/assistant/messages", response_model=AssistantAnswerRead)
def create_assistant_message(
    ticket_id: str,
    payload: AssistantMessageRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    provider: ChatCompletionProvider = Depends(get_chat_provider),
) -> AssistantAnswerRead:
    try:
        record = assistant.answer_ticket_question(
            session,
            ticket_id,
            user,
            payload.question,
            embedder=embedder,
            provider=provider,
        )
    except TicketNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        ) from error
    except AssistantFormatError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant returned an unreadable answer. Retry the question.",
        ) from error
    except (RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The model service is unavailable. Check provider settings and connectivity.",
        ) from error

    return _to_read(record)


def _to_read(record: AssistantAnswerRecord) -> AssistantAnswerRead:
    return AssistantAnswerRead(
        session_id=record.session_id,
        answer=record.answer,
        uncertainty=record.uncertainty,
        has_evidence=record.has_evidence,
        citations=[
            AssistantCitationRead(
                chunk_id=citation.chunk_id,
                document_id=citation.document_id,
                document_title=citation.document_title,
                section=citation.section,
                source_type=citation.source_type,
                content=citation.content,
                score=citation.score,
            )
            for citation in record.citations
        ],
        next_best_action=_next_best_action_read(record),
        summary=(
            AssistantSummaryRead(
                problem=record.summary.problem,
                solution=record.summary.solution,
                product_recommendation=record.summary.product_recommendation,
                actions=record.summary.actions,
            )
            if record.summary
            else None
        ),
        action_intent=record.action_intent,
    )


def _next_best_action_read(record: AssistantAnswerRecord) -> NextBestActionRead | None:
    action = record.next_best_action
    if action is None:
        return None
    return NextBestActionRead(
        remediation=action.remediation,
        dispatch_required=action.dispatch_required,
        suggestion=action.suggestion,
        evidence=action.evidence,
        suggestion_evidence=action.suggestion_evidence,
    )
