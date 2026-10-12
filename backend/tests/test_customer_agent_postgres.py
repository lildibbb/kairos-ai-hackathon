"""Opt-in action concurrency tests in the appointment test's disposable schema."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.customer_chat_schemas import CustomerChatRequest
from app.domain.models import AuditEvent, CustomerChatTurn, CustomerRouterState
from app.integrations.embeddings import LocalDeterministicEmbeddingProvider
from app.integrations.model_provider import LocalDeterministicChatProvider
from app.services.customer_chat import answer_customer
from test_customer_chat import NOW, ask, workspace  # noqa: F401
from test_customer_agent import config
from test_customer_appointments_postgres import db_session, pytestmark  # noqa: F401


def test_competing_confirmation_retries_execute_router_action_once(workspace):
    session, _, _, actors = workspace
    first = ask(workspace, "Please reboot my router", settings=config(workspace))
    engine = session.get_bind()
    session.rollback()
    barrier = Barrier(2)
    request_id = uuid4()

    def execute():
        with Session(engine, expire_on_commit=False) as transaction:
            barrier.wait(timeout=10)
            return answer_customer(transaction, actors[0],
                CustomerChatRequest(message="Confirm action", conversation_id=first.conversation_id,
                    request_id=request_id, answer_choice="confirm_router_action", action_id=first.router_action.id),
                settings=config(workspace), embedder=LocalDeterministicEmbeddingProvider(),
                provider=LocalDeterministicChatProvider(), now=NOW).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(), range(2)))
    assert results == ["action_completed", "action_completed"]
    assert session.scalar(select(CustomerRouterState.reboot_count)) == 1
    assert session.scalar(select(func.count()).select_from(CustomerChatTurn).where(CustomerChatTurn.request_id == str(request_id))) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == "customer_router_action_executed")) == 1
