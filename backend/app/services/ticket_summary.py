"""Ticket AI summary: summarize.py over the ticket's facts plus retrieved KB evidence.

The result is the same PROBLEM / SUGGESTION / ACTIONS contract that
``app/summarize.py`` writes for its batch run, and it is cached in the same
``customer_summaries`` table so the batch job and the ticket page agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai import retrieval
from app.ai.ports import ChatCompletionProvider, ChunkMatch, EmbeddingProvider
from app.ai.summarization import (
    ReasonedSummary,
    SummarizerUnavailable,
    build_customer_facts,
    product_recommendation_text,
    summarize_matches,
)
from app.auth.dependencies import AuthenticatedUser
from app.config import get_settings
from app.domain.models import CustomerSummary
from app.services import ticket_queries
from app.services.service_orders import OrderOption, order_options, plan_price


@dataclass(frozen=True)
class TicketSummaryRecord:
    ticket_id: str
    problem: str
    solution: str | None
    product_recommendation: str | None
    actions: list[str]
    facts: list[str]
    citations: list[ChunkMatch]
    order_options: list[OrderOption]
    plan_name: str | None
    plan_price_myr: float | None
    model: str | None
    generated_at: datetime | None
    cached: bool


def plan_name_for(detail: ticket_queries.TicketDetailRecord) -> str | None:
    for service in detail.services:
        if service.service_type.upper() == "HSI":
            name = (service.details or {}).get("plan_name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def get_ticket_summary(
    session: Session,
    ticket_id: str,
    actor: AuthenticatedUser,
    *,
    embedder: EmbeddingProvider,
    provider: ChatCompletionProvider,
    refresh: bool = False,
) -> TicketSummaryRecord:
    detail = ticket_queries.get_ticket_detail(session, ticket_id, actor)
    login_id = detail.customer.customer_ref
    devices = [device.source for device in detail.devices]
    plan_name = plan_name_for(detail)
    price = plan_price(plan_name)
    facts = build_customer_facts(login_id, devices, detail.routers, plan_name, price)
    query = f"{detail.ticket.summary}\n{_recommended_lines(facts)}"
    matches = retrieval.retrieve_for_ticket(session, ticket_id, actor, query, embedder, limit=4)

    cached = session.get(CustomerSummary, login_id)
    if cached is not None and cached.actions is not None and not refresh:
        actions = [item for item in cached.actions.split(",") if item]
        reasoned = ReasonedSummary(
            problem=cached.summary,
            solution=cached.recommendation,
            product_recommendation=product_recommendation_text(actions, facts),
            actions=actions,
            facts=facts,
        )
        return _record(ticket_id, reasoned, matches, plan_name, cached.model, cached.generated_at, cached=True)

    reasoned = summarize_matches(
        login_id=login_id,
        devices=devices,
        routers=detail.routers,
        matches=matches,
        provider=provider,
        plan_name=plan_name,
        ticket_note=detail.ticket.summary,
        plan_price=price,
    )
    model = get_settings().model_name
    generated_at = datetime.now()
    _save(session, login_id, reasoned, model, generated_at)
    return _record(ticket_id, reasoned, matches, plan_name, model, generated_at, cached=False)


def _save(session: Session, login_id: str, reasoned: ReasonedSummary, model: str | None, generated_at: datetime) -> None:
    """Upsert the cached row; a concurrent request may have inserted it first."""
    for attempt in range(2):
        cached = session.get(CustomerSummary, login_id)
        if cached is None:
            cached = CustomerSummary(login_id=login_id, summary=reasoned.problem)
            session.add(cached)
        cached.summary = reasoned.problem
        cached.recommendation = reasoned.solution
        cached.actions = ",".join(reasoned.actions)
        cached.model = model
        cached.generated_at = generated_at
        try:
            session.commit()
            return
        except IntegrityError:
            session.rollback()
            if attempt:
                raise


def _record(
    ticket_id: str,
    reasoned: ReasonedSummary,
    matches: list[ChunkMatch],
    plan_name: str | None,
    model: str | None,
    generated_at: datetime | None,
    *,
    cached: bool,
) -> TicketSummaryRecord:
    return TicketSummaryRecord(
        ticket_id=ticket_id,
        problem=reasoned.problem,
        solution=reasoned.solution,
        product_recommendation=reasoned.product_recommendation,
        actions=reasoned.actions,
        facts=[line for line in reasoned.facts.splitlines() if line.strip()],
        citations=matches,
        order_options=order_options(reasoned.actions, plan_name),
        plan_name=plan_name,
        plan_price_myr=plan_price(plan_name),
        model=model,
        generated_at=generated_at,
        cached=cached,
    )


def _recommended_lines(facts: str) -> str:
    return "\n".join(line for line in facts.splitlines() if line.startswith("Recommended action"))


__all__ = ["SummarizerUnavailable", "TicketSummaryRecord", "get_ticket_summary", "plan_name_for"]
