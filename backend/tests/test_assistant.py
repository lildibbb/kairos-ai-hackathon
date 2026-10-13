import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.chunking import chunk_id_for
from app.ai.ingestion import embed_missing_chunks
from app.api.assistant import get_chat_provider, get_embedding_provider
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.session import get_session
from app.domain.models import (
    AssistantMessage,
    AssistantSession,
    Customer,
    KnowledgeChunk,
    KnowledgeDocument,
    NetworkDevice,
    NetworkEvent,
    Role,
    Service,
    Ticket,
    TopologyEdge,
    User,
)
from app.integrations.embeddings import LocalDeterministicEmbeddingProvider
from app.integrations.model_provider import LocalDeterministicChatProvider
from app.main import app
from app.services import assistant

ONU_INSPECT_CHUNK = chunk_id_for("kb-onu-offline-v1", "1.0", "Inspect optical path")
ONU_ESCALATE_CHUNK = chunk_id_for("kb-onu-offline-v1", "1.0", "Escalate")


class StaticChatProvider:
    """Returns a fixed payload and records the prompts it received."""

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[list[object]] = []

    def complete(self, messages, *, temperature: float = 0.0) -> str:
        self.calls.append(list(messages))
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload)


@pytest.fixture
def embedder() -> LocalDeterministicEmbeddingProvider:
    return LocalDeterministicEmbeddingProvider(1024)


def _workspace(session: Session) -> dict[str, object]:
    technician_role = Role(name="technician")
    session.add(technician_role)
    session.flush()

    technician = User(
        email="technician@test.invalid",
        display_name="Test Technician",
        password_hash="synthetic-test-hash",
        role_id=technician_role.id,
        is_active=True,
    )
    customer = Customer(customer_ref="CUST-1", name="Test Customer", address="1 Test Way")
    session.add_all([technician, customer])
    session.flush()

    service = Service(
        customer_id=customer.id,
        service_type="Granite",
        service_ref="SVC-1",
        status="active",
        details={"account_ref": "ACC-1"},
    )
    device = NetworkDevice(
        customer_id=customer.id,
        device_ref="DEV-1",
        device_type="ONU",
        name="Test ONU",
        status="offline",
        details={"rx_power_dbm": -28.1, "admin_password": "must-not-enter-prompt"},
    )
    session.add_all([service, device])
    session.flush()

    event = NetworkEvent(
        source_event_id="EVT-1",
        event_type="ONU_OFFLINE",
        device_id=device.id,
        service_id=service.id,
        payload={"signal_state": "no_link"},
    )
    session.add(event)
    session.flush()

    ticket = Ticket(
        source_event_id=event.id,
        customer_id=customer.id,
        service_id=service.id,
        assigned_technician_id=technician.id,
        severity="high",
        status="open",
        summary="ONU offline at the test customer",
    )
    session.add(ticket)
    session.commit()

    return {"technician": technician, "ticket": ticket}


def _technician_actor(workspace: dict[str, object]) -> AuthenticatedUser:
    technician = workspace["technician"]
    return AuthenticatedUser(id=technician.id, email=technician.email, role="technician")


def _add_document(
    session: Session,
    *,
    document_key: str,
    title: str,
    source_type: str,
    sections: dict[str, str],
    version: str = "1.0",
) -> None:
    session.add(
        KnowledgeDocument(
            id=document_key,
            document_key=document_key,
            title=title,
            source_type=source_type,
            version=version,
        )
    )
    for section, content in sections.items():
        session.add(
            KnowledgeChunk(
                id=chunk_id_for(document_key, version, section),
                document_id=document_key,
                section=section,
                content=content,
            )
        )
    session.flush()


def _seed_corpus(session: Session, embedder) -> None:
    _add_document(
        session,
        document_key="kb-onu-offline-v1",
        title="ONU Offline Field Checks",
        source_type="curated_procedure",
        sections={
            "Confirm service impact": (
                "Check whether the reported loss affects one endpoint or the whole access segment."
            ),
            "Inspect optical path": (
                "Verify the patch lead is seated and inspect for visible bends or damage."
            ),
            "Escalate": (
                "If the ONU stays offline, record optical readings and escalate through network operations."
            ),
        },
    )
    _add_document(
        session,
        document_key="kb-optical-loss-v1",
        title="Optical Loss Triage",
        source_type="curated_procedure",
        sections={
            "Field inspection": "Inspect connectors and cable routing for contamination or tight bends.",
            "Record and route": "Record the measured receive level and escalate shared-path loss.",
        },
    )
    embed_missing_chunks(session, embedder)
    session.commit()


def test_authorized_question_returns_cited_answer(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Recommendation: inspect the optical path before dispatch.",
            "citations": [
                {
                    "chunk_id": ONU_INSPECT_CHUNK,
                    "document_title": "ONU Offline Field Checks",
                    "section": "Inspect optical path",
                }
            ],
            "uncertainty": "Field conditions vary.",
            "next_best_action": {
                "remediation": "Reseat the patch lead and recheck.",
                "dispatch_required": False,
                "suggestion": None,
                "evidence": [ONU_INSPECT_CHUNK],
                "suggestion_evidence": [],
            },
        }
    )

    record = assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "How do I resolve an offline ONU?",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    assert record.has_evidence is True
    assert [citation.chunk_id for citation in record.citations] == [ONU_INSPECT_CHUNK]
    assert record.citations[0].document_title == "ONU Offline Field Checks"
    assert record.citations[0].content
    assert record.next_best_action is not None
    assert record.next_best_action.evidence == [ONU_INSPECT_CHUNK]
    assert provider.calls, "the model provider should be asked for the structured answer"

    stored = db_session.scalars(select(AssistantMessage)).all()
    assert {message.role for message in stored} == {"user", "assistant"}
    session_row = db_session.scalar(select(AssistantSession))
    assert session_row is not None


def test_follow_up_turn_receives_bounded_persisted_history_and_topology(db_session, embedder):
    workspace = _workspace(db_session)
    onu = db_session.scalar(select(NetworkDevice).where(NetworkDevice.device_ref == "DEV-1"))
    router = NetworkDevice(
        customer_id=onu.customer_id,
        device_ref="DEV-ROUTER-1",
        device_type="router",
        name="Test Router",
        status="online",
    )
    db_session.add(router)
    db_session.flush()
    db_session.add(
        TopologyEdge(
            source_device_id=onu.id,
            target_device_id=router.id,
            service_id=workspace["ticket"].service_id,
        )
    )
    db_session.commit()
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Check the patch lead, then record the optical reading.",
            "citations": [{"chunk_id": ONU_INSPECT_CHUNK}],
            "uncertainty": "",
            "next_best_action": None,
        }
    )
    actor = _technician_actor(workspace)

    assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        actor,
        "The ONU is offline",
        embedder=embedder,
        provider=provider,
        limit=10,
    )
    assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        actor,
        "What should I record?",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    second_prompt = provider.calls[1][1].content
    assert '"The ONU is offline"' in second_prompt
    assert '"Check the patch lead, then record the optical reading."' in second_prompt
    assert "Service Granite SVC-1 (active)" in second_prompt
    assert "Topology: DEV-1 -> DEV-ROUTER-1" in second_prompt
    assert "signal_state=no_link" in second_prompt
    assert "rx_power_dbm=-28.1" in second_prompt
    assert "must-not-enter-prompt" not in second_prompt
    assert "Treat the technician question, conversation history" in provider.calls[1][0].content


def test_hallucinated_citations_are_dropped(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Recommendation: inspect the optical path.",
            "citations": [
                {"chunk_id": "kb-invented-v9:1.0:nothing", "document_title": "Fake", "section": "Fake"},
                {"chunk_id": ONU_INSPECT_CHUNK, "document_title": "ONU Offline Field Checks", "section": "Inspect optical path"},
            ],
            "uncertainty": "",
            "next_best_action": {
                "remediation": "Reseat the patch lead.",
                "dispatch_required": False,
                "evidence": ["kb-invented-v9:1.0:nothing", ONU_ESCALATE_CHUNK],
            },
        }
    )

    record = assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "offline onu",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    assert [citation.chunk_id for citation in record.citations] == [ONU_INSPECT_CHUNK]
    assert record.next_best_action is not None
    assert record.next_best_action.evidence == [ONU_ESCALATE_CHUNK]


def test_only_invalid_citations_leave_no_sourced_answer(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Trust me, this is the fix.",
            "citations": [{"chunk_id": "kb-invented-v9:1.0:nothing"}],
            "uncertainty": "",
            "next_best_action": {
                "remediation": "Do the invented thing.",
                "dispatch_required": False,
                "evidence": ["kb-invented-v9:1.0:nothing"],
            },
        }
    )

    record = assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "offline onu",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    assert record.citations == []
    assert record.has_evidence is False
    assert record.next_best_action is not None
    assert record.next_best_action.evidence == []


def test_no_kb_match_still_answers_from_health_facts_without_citations(db_session, embedder):
    workspace = _workspace(db_session)
    provider = StaticChatProvider(
        {"answer": "fabricated", "citations": [{"chunk_id": "kb-x:1.0:y"}], "uncertainty": ""}
    )

    record = assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "How do I resolve an offline ONU?",
        embedder=embedder,
        provider=provider,
    )

    assert record.has_evidence is False
    assert record.citations == []
    assert record.next_best_action is None
    assert record.answer == "fabricated"
    assert "health facts (summarize.py engine)" in provider.calls[0][1].content


def test_unsupported_suggestion_is_omitted(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Recommendation: inspect the optical path.",
            "citations": [{"chunk_id": ONU_INSPECT_CHUNK}],
            "uncertainty": "",
            "next_best_action": {
                "remediation": "Reseat the patch lead.",
                "dispatch_required": False,
                "suggestion": "Upgrade the customer to NextGen fibre.",
                "evidence": [ONU_INSPECT_CHUNK],
                "suggestion_evidence": [],
            },
        }
    )

    record = assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "offline onu",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    assert record.next_best_action is not None
    assert record.next_best_action.remediation == "Reseat the patch lead."
    assert record.next_best_action.suggestion is None
    assert record.next_best_action.suggestion_evidence == []


def test_uncited_remediation_is_kept_as_inference(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Answer without advice.",
            "citations": [{"chunk_id": ONU_INSPECT_CHUNK}],
            "uncertainty": "",
            "next_best_action": {
                "remediation": "Do something unwarranted.",
                "dispatch_required": True,
                "evidence": [],
                "suggestion_evidence": [],
            },
        }
    )

    record = assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "offline onu",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    assert record.next_best_action is not None
    assert record.next_best_action.remediation == "Do something unwarranted."
    assert record.next_best_action.evidence == []


def test_prose_model_response_is_kept_uncited(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider("not a json object")

    record = assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "offline onu",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    assert record.answer == "not a json object"
    assert record.citations == []


def test_empty_model_response_raises_format_error(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider("{}")

    with pytest.raises(assistant.AssistantFormatError):
        assistant.answer_ticket_question(
            db_session,
            workspace["ticket"].id,
            _technician_actor(workspace),
            "offline onu",
            embedder=embedder,
            provider=provider,
            limit=10,
        )


def test_messages_are_persisted_with_credentials_redacted(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Recommendation: inspect the optical path.",
            "citations": [{"chunk_id": ONU_INSPECT_CHUNK}],
            "uncertainty": "",
            "next_best_action": None,
        }
    )

    assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "The customer read password=SuperSecret-42 aloud, how do I reset the ONU?",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    messages = db_session.scalars(select(AssistantMessage)).all()
    by_role = {message.role: message for message in messages}
    user_message = by_role["user"]
    assert "SuperSecret-42" not in user_message.content
    assert "[redacted]" in user_message.content
    assistant_message = by_role["assistant"]
    assert assistant_message.citations
    assert all("content" not in citation for citation in assistant_message.citations)


def test_unauthorized_ticket_is_denied(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    intruder = AuthenticatedUser(id="someone-else", email="intruder@test.invalid", role="technician")
    provider = StaticChatProvider({"answer": "nope", "citations": []})

    with pytest.raises(HTTPException) as error:
        assistant.answer_ticket_question(
            db_session,
            workspace["ticket"].id,
            intruder,
            "offline onu",
            embedder=embedder,
            provider=provider,
            limit=10,
        )

    assert error.value.status_code == 404
    assert provider.calls == []


def test_local_provider_returns_a_grounded_structured_answer(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)

    record = assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "offline onu optical path",
        embedder=embedder,
        provider=LocalDeterministicChatProvider(),
        limit=10,
    )

    indexed_ids = {chunk.id for chunk in db_session.scalars(select(KnowledgeChunk)).all()}
    assert record.citations
    assert all(citation.chunk_id in indexed_ids for citation in record.citations)
    assert record.next_best_action is not None
    assert record.next_best_action.evidence


def test_prompt_requires_structured_grounded_answer_without_chain_of_thought(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Recommendation: inspect the optical path.",
            "citations": [{"chunk_id": ONU_INSPECT_CHUNK}],
            "uncertainty": "",
            "next_best_action": None,
        }
    )

    assistant.answer_ticket_question(
        db_session,
        workspace["ticket"].id,
        _technician_actor(workspace),
        "offline onu",
        embedder=embedder,
        provider=provider,
        limit=10,
    )

    system_prompt = provider.calls[0][0].content
    assert "citations" in system_prompt
    assert "next_best_action" in system_prompt
    assert "health facts" in system_prompt
    assert "label that part as Inference" in system_prompt
    assert "never invent a citation" in system_prompt
    assert "do not include hidden chain-of-thought" in system_prompt


def test_assistant_endpoint_returns_citations_and_denies_other_technicians(db_session, embedder):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    provider = StaticChatProvider(
        {
            "answer": "Recommendation: inspect the optical path.",
            "citations": [{"chunk_id": ONU_INSPECT_CHUNK}],
            "uncertainty": "",
            "next_best_action": {
                "remediation": "Reseat the patch lead.",
                "dispatch_required": False,
                "evidence": [ONU_INSPECT_CHUNK],
            },
        }
    )

    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: _technician_actor(workspace)
    app.dependency_overrides[get_embedding_provider] = lambda: embedder
    app.dependency_overrides[get_chat_provider] = lambda: provider
    try:
        allowed = TestClient(app).post(
            f"/tickets/{workspace['ticket'].id}/assistant/messages",
            json={"question": "How do I resolve an offline ONU?"},
        )
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id="someone-else", email="intruder@test.invalid", role="technician"
        )
        denied = TestClient(app).post(
            f"/tickets/{workspace['ticket'].id}/assistant/messages",
            json={"question": "How do I resolve an offline ONU?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert allowed.status_code == 200
    body = allowed.json()
    assert body["has_evidence"] is True
    assert [citation["chunk_id"] for citation in body["citations"]] == [ONU_INSPECT_CHUNK]
    assert body["next_best_action"]["evidence"] == [ONU_INSPECT_CHUNK]
    assert denied.status_code == 404


def test_assistant_websocket_streams_authorized_grounded_answer(db_session, embedder, monkeypatch):
    workspace = _workspace(db_session)
    _seed_corpus(db_session, embedder)
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_embedding_provider] = lambda: embedder
    app.dependency_overrides[get_chat_provider] = lambda: LocalDeterministicChatProvider()
    try:
        monkeypatch.setattr("app.api.assistant.decode_access_token", lambda token: {"sub": workspace["technician"].id, "role": "technician"})
        with TestClient(app).websocket_connect(
            f"/tickets/{workspace['ticket'].id}/assistant/stream?token=unused"
        ) as websocket:
            assert websocket.receive_json()["type"] == "ready"
            websocket.send_json({"question": "offline ONU optical path"})
            assert websocket.receive_json()["type"] == "retrieval_started"
            steps = []
            answer = websocket.receive_json()
            while answer["type"] == "step":
                steps.append(answer)
                answer = websocket.receive_json()
            complete = websocket.receive_json()
    finally:
        app.dependency_overrides.clear()

    assert any(step["id"] == "retrieval" and step["status"] == "done" for step in steps)
    assert answer["type"] == "answer"
    assert answer["data"]["has_evidence"] is True
    assert answer["data"]["citations"]
    assert complete["type"] == "complete"
