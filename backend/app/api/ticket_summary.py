import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.ports import ChatCompletionProvider, EmbeddingProvider
from app.api.assistant import get_chat_provider, get_embedding_provider
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.config import get_settings
from app.db.session import get_session
from app.domain.assistant_schemas import AssistantCitationRead
from app.domain.models import ServiceOrder
from app.domain.order_schemas import (
    OrderCreateRequest,
    OrderOptionRead,
    OrderProductRead,
    OrderRead,
    TicketSummaryRead,
)
from app.services import service_orders, ticket_summary
from app.services.ticket_queries import TicketNotFoundError

router = APIRouter(prefix="/tickets", tags=["summary"])


@router.get("/{ticket_id}/summary", response_model=TicketSummaryRead)
def get_ticket_summary(
    ticket_id: str,
    refresh: bool = False,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    provider: ChatCompletionProvider = Depends(get_chat_provider),
) -> TicketSummaryRead:
    try:
        record = ticket_summary.get_ticket_summary(
            session, ticket_id, user, embedder=embedder, provider=provider, refresh=refresh
        )
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error
    except ticket_summary.SummarizerUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The summarizer is unavailable") from error
    except (RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The model service is unavailable. Check provider settings and connectivity.",
        ) from error
    return TicketSummaryRead(
        ticket_id=record.ticket_id,
        problem=record.problem,
        solution=record.solution,
        product_recommendation=record.product_recommendation,
        actions=record.actions,
        facts=record.facts,
        citations=[
            AssistantCitationRead(
                chunk_id=match.chunk_id,
                document_id=match.document_id,
                document_title=match.document_title,
                section=match.section,
                source_type=match.source_type,
                content=match.content,
                score=match.score,
            )
            for match in record.citations
        ],
        order_options=[
            OrderOptionRead(
                action=option.action,
                label=option.label,
                recommended=option.recommended,
                products=[
                    OrderProductRead(
                        code=product.code,
                        name=product.name,
                        description=product.description,
                        monthly_price_myr=product.monthly_price_myr,
                        one_time_price_myr=product.one_time_price_myr,
                        speed_mbps=product.speed_mbps,
                        tier=product.tier,
                        features=list(product.features),
                        badge=product.badge,
                    )
                    for product in option.products
                ],
            )
            for option in record.order_options
        ],
        plan_name=record.plan_name,
        plan_price_myr=record.plan_price_myr,
        model=record.model,
        generated_at=record.generated_at,
        cached=record.cached,
    )


@router.get("/{ticket_id}/orders", response_model=list[OrderRead])
def list_orders(
    ticket_id: str,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[OrderRead]:
    try:
        return [_order_read(order) for order in service_orders.list_orders(session, ticket_id, user)]
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error


@router.post("/{ticket_id}/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    ticket_id: str,
    payload: OrderCreateRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> OrderRead:
    try:
        record = service_orders.submit_order(
            session,
            ticket_id,
            user,
            action=payload.action,
            product_code=payload.product_code,
            notes=payload.notes,
            settings=get_settings(),
        )
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error
    except service_orders.OrderValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return _order_read(record.order)


def _order_read(order: ServiceOrder) -> OrderRead:
    return OrderRead(
        id=order.id,
        ticket_id=order.ticket_id,
        action=order.action,
        product_code=order.product_code,
        product_name=order.product_name,
        monthly_price_myr=order.monthly_price_myr,
        one_time_price_myr=order.one_time_price_myr,
        notes=order.notes,
        status=order.status,
        email_status=order.email_status,
        email_recipient=order.email_recipient,
        email_error=order.email_error,
        created_at=order.created_at,
    )
