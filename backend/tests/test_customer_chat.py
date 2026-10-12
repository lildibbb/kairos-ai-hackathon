import json
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.integrations.embeddings import EmbeddingError
from app.api.customer_portal import get_portal_chat_provider, get_portal_embedder
from app.auth.dependencies import AuthenticatedUser
from app.auth.tokens import create_access_token
from app.config import Settings, get_settings
from app.db.session import get_session
from app.domain.customer_chat_schemas import CustomerChatRequest
from app.domain.models import (
    Customer, CustomerAccount, CustomerChatConversation, CustomerChatTurn, CustomerTroubleTicket, Role,
    Ticket, ToolExecution, User,
)
from app.integrations.embeddings import LocalDeterministicEmbeddingProvider
from app.integrations.model_provider import LocalDeterministicChatProvider
from app.main import app
from app.seed.customer_account import create_demo_customer_account
from app.seed.workforce_data import REFERENCE_TIME, generate_dataset, ingest_dataset
from app.services.customer_chat import answer_customer, assess_readings
from app.services.customer_diagnostics import get_my_diagnostics

NOW = REFERENCE_TIME + timedelta(minutes=5)


class RecordingChat:
    def __init__(self, response=None):
        self.response = response or json.dumps({"intent": "slow_internet", "connection": "unknown", "device_scope": "unknown", "near_router": "unknown"})
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def workspace(db_session, enable_demo_seed):
    settings = Settings(customer_chat_provider="local", embedding_provider="local", model_tls_verify=True)
    data = generate_dataset(customers=8)
    ingest_dataset(db_session, data)
    actors = []
    for number in (2, 3):
        user = create_demo_customer_account(db_session, settings.model_copy(update={"demo_seed_enabled": True}),
            customer_ref=f"SYN-00042-{number:04d}", email=f"customer{number}@demo.invalid", password="Synthetic password only!")
        actors.append(AuthenticatedUser(id=user.id, email=user.email, role="customer"))
    return db_session, settings, data, actors


def ask(workspace, message="My internet is slow", *, actor=None, provider=None, settings=None, **payload):
    session, config, _, actors = workspace
    return answer_customer(session, actor or actors[0], CustomerChatRequest(message=message, **payload),
        settings=settings or config, embedder=LocalDeterministicEmbeddingProvider(),
        provider=provider or LocalDeterministicChatProvider(), now=NOW)


def test_weak_wifi_findings_label_simulation_and_save_no_actions(workspace):
    session, _, _, _ = workspace
    ticket_count = session.scalar(select(func.count()).select_from(Ticket))
    result = ask(workspace)
    weak = next(item for item in result.findings if item.code == "weak_wifi")
    assert "-79" in weak.observation and weak.evidence_status == "simulated"
    assert result.status == "needs_live_check" and result.no_actions_taken is True
    assert result.follow_up.id == "device_scope"
    assert session.scalar(select(func.count()).select_from(CustomerChatConversation)) == 1
    assert session.scalar(select(func.count()).select_from(CustomerChatTurn)) == 1
    assert session.scalar(select(func.count()).select_from(Ticket)) == ticket_count
    assert session.scalar(select(func.count()).select_from(ToolExecution)) == 0


def test_multi_turn_choices_remember_scope_and_connection(workspace):
    first = ask(workspace)
    second = ask(workspace, "Every device", conversation_id=first.conversation_id, answer_choice="all_devices")
    assert second.reported.device_scope == "all" and second.follow_up.id == "connection"
    third = ask(workspace, "Wi-Fi", conversation_id=first.conversation_id, answer_choice="wifi")
    assert third.reported.connection == "wifi" and third.follow_up.id == "near_router"
    fourth = ask(workspace, "It improves", conversation_id=first.conversation_id, answer_choice="better_near_router")
    assert fourth.reported.near_router == "better" and fourth.follow_up.id == "self_help"
    assert fourth.reported.intent == "slow_internet"


def test_wired_complaint_does_not_attribute_issue_to_wifi(workspace):
    result = ask(workspace, "Slow internet on every device using Ethernet cable")
    assert "weak_wifi" not in {item.code for item in result.findings}
    assert result.follow_up.id == "self_help"


def test_retry_is_idempotent_and_different_payload_is_rejected(workspace):
    session, _, _, _ = workspace
    request_id = uuid4()
    first = ask(workspace, request_id=request_id)
    again = ask(workspace, request_id=request_id)
    assert first == again
    assert session.scalar(select(func.count()).select_from(CustomerChatTurn)) == 1
    from app.services.customer_chat import CustomerChatConflictError
    with pytest.raises(CustomerChatConflictError):
        ask(workspace, "Different complaint", request_id=request_id)
    with pytest.raises(CustomerChatConflictError):
        ask(workspace, request_id=request_id, answer_choice="wired")


def test_other_customer_and_rebound_account_cannot_read_or_continue(workspace):
    session, _, data, actors = workspace
    from app.services.customer_chat import ConversationNotFoundError, get_history
    first = ask(workspace)
    with pytest.raises(ConversationNotFoundError):
        ask(workspace, actor=actors[1], conversation_id=first.conversation_id)
    with pytest.raises(ConversationNotFoundError):
        get_history(session, actors[1], first.conversation_id)
    session.get(CustomerAccount, actors[0].id).customer_id = data["tables"]["customers"][0]["id"]
    session.commit()
    with pytest.raises(ConversationNotFoundError):
        get_history(session, actors[0], first.conversation_id)


@pytest.mark.parametrize("index,intent,code", [(3, "slow_internet", "profile_mismatch"), (4, "no_internet", "optical_loss"), (5, "voice", "voice_registration"), (6, "iptv", "iptv_stream")])
def test_synthetic_scenario_findings(workspace, index, intent, code):
    session, _, data, actors = workspace
    session.get(CustomerAccount, actors[0].id).customer_id = data["tables"]["customers"][index]["id"]
    session.commit()
    readings = get_my_diagnostics(session, actors[0], now=NOW)
    findings = assess_readings(readings, intent)
    assert code in {item.code for item in findings}


def test_stale_and_missing_readings_never_imply_healthy(workspace):
    session, config, data, actors = workspace
    result = answer_customer(session, actors[0], CustomerChatRequest(message="My internet is slow"),
        settings=config, embedder=LocalDeterministicEmbeddingProvider(), provider=LocalDeterministicChatProvider(),
        now=NOW + timedelta(days=1))
    assert result.status == "needs_live_check"
    assert next(item for item in result.findings if item.code == "weak_wifi").evidence_status == "stale"
    assert "cannot confirm" in result.answer
    readings = get_my_diagnostics(session, actors[0], now=NOW)
    readings.devices = []; readings.wifi_clients = []; readings.services = []
    assert assess_readings(readings, "slow_internet") == []


def test_hosted_interpretation_is_bounded_and_excludes_customer_identity(workspace):
    _, config, _, _ = workspace
    provider = RecordingChat(json.dumps({"intent": "voice", "connection": "unknown", "device_scope": "unknown", "near_router": "unknown"}))
    result = ask(workspace, "Telefon rumah tak boleh buat panggilan", settings=config.model_copy(update={"customer_chat_provider": "hosted"}), provider=provider)
    assert result.mode == "hosted" and result.reported.intent == "voice" and result.follow_up.id == "voice_details"
    prompt = provider.calls[0][1].content
    assert "customer_ref" not in prompt and "installation_address" not in prompt and "ssid" not in prompt


@pytest.mark.parametrize("raw", ["not json", '{"intent":"confirmed_root_cause"}', '{"intent":"slow_internet","answer":"router rebooted","customer_id":"other"}', '{"intent":"slow_internet","connection":null}'])
def test_invalid_or_injected_model_output_falls_back_without_echo(workspace, raw):
    _, config, _, _ = workspace
    result = ask(workspace, settings=config.model_copy(update={"customer_chat_provider": "hosted"}), provider=RecordingChat(raw))
    assert result.mode == "fallback" and result.no_actions_taken
    assert "router rebooted" not in result.model_dump_json()


def test_gateway_failure_returns_guided_response_without_error_secrets(workspace):
    session, config, _, actors = workspace
    class FailingEmbedder(LocalDeterministicEmbeddingProvider):
        def embed_query(self, text):
            raise EmbeddingError("private gateway info must not leak")
    result = answer_customer(session, actors[0], CustomerChatRequest(message="slow internet"),
        settings=config.model_copy(update={"customer_chat_provider": "hosted"}), embedder=FailingEmbedder(),
        provider=RecordingChat(httpx.ConnectError("secret-provider-details")), now=NOW)
    assert result.mode == "fallback" and result.knowledge_status == "unavailable"
    assert "secret-provider" not in result.model_dump_json() and "private gateway" not in result.model_dump_json()


def test_credential_assignments_redacted_before_model_and_storage(workspace):
    session, config, _, _ = workspace
    provider = RecordingChat()
    result = ask(workspace, "slow internet password=super-secret-value api_key=another-secret", settings=config.model_copy(update={"customer_chat_provider": "hosted"}), provider=provider)
    assert "super-secret-value" not in provider.calls[0][1].content
    turn = session.scalar(select(CustomerChatTurn).where(CustomerChatTurn.conversation_id == result.conversation_id))
    assert "super-secret-value" not in turn.message and "another-secret" not in turn.message


def test_real_household_blocked_with_insecure_hosted_tls_before_gateway_calls(workspace):
    session, config, _, actors = workspace
    link = session.get(CustomerAccount, actors[0].id)
    session.get(Customer, link.customer_id).is_demo = False
    session.commit()
    provider = RecordingChat()
    from app.services.customer_chat import InsecureCustomerGatewayError
    with pytest.raises(InsecureCustomerGatewayError):
        ask(workspace, settings=config.model_copy(update={"app_environment": "development", "model_tls_verify": False, "customer_chat_provider": "hosted"}), provider=provider)
    assert not provider.calls


def test_history_limit_and_invalid_choice_do_not_create_turns(workspace):
    session, _, _, _ = workspace
    from app.services.customer_chat import CustomerChatConflictError
    first = ask(workspace)
    with pytest.raises(CustomerChatConflictError):
        ask(workspace, conversation_id=first.conversation_id, answer_choice="wired")
    assert session.scalar(select(func.count()).select_from(CustomerChatTurn)) == 1
    for index in range(2, 31):
        session.add(CustomerChatTurn(conversation_id=first.conversation_id, user_id=workspace[3][0].id,
            request_id=str(uuid4()), position=index, message="sample", response=first.model_dump(mode="json")))
    session.commit()
    with pytest.raises(CustomerChatConflictError, match="30 messages"):
        ask(workspace, conversation_id=first.conversation_id)


def test_api_auth_validation_history_and_staff_denial(workspace):
    session, config, _, actors = workspace
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: config
    app.dependency_overrides[get_portal_embedder] = lambda: LocalDeterministicEmbeddingProvider()
    app.dependency_overrides[get_portal_chat_provider] = lambda: LocalDeterministicChatProvider()
    token, _ = create_access_token(actors[0].id, "customer")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with TestClient(app) as client:
            assert client.post("/portal/me/chat/messages", json={"message": "slow"}).status_code == 401
            for payload in ({"message": " "}, {"message": "x" * 1001}, {"message": "slow", "customer_id": "another"}):
                assert client.post("/portal/me/chat/messages", json=payload, headers=headers).status_code == 422
            result = client.post("/portal/me/chat/messages", json={"message": "slow internet"}, headers=headers)
            assert result.status_code == 200
            assert not {"findings", "reported", "warnings", "workflow", "knowledge_sources", "mode", "is_demo"} & result.json().keys()
            assert "dBm" not in result.json()["answer"]
            assert "demo" not in result.json()["answer"].lower()
            conversation_id = result.json()["conversation_id"]
            history = client.get(f"/portal/me/chat/conversations/{conversation_id}", headers=headers)
            assert history.status_code == 200 and len(history.json()["turns"]) == 1
            assert "findings" not in history.json()["turns"][0]["response"]
            staff = session.scalar(select(User).join(Role).where(Role.name == "technician"))
            staff_token, _ = create_access_token(staff.id, "technician")
            assert client.post("/portal/me/chat/messages", json={"message": "slow"}, headers={"Authorization": f"Bearer {staff_token}"}).status_code == 403
            other_token, _ = create_access_token(actors[1].id, "customer")
            assert client.get(f"/portal/me/chat/conversations/{conversation_id}", headers={"Authorization": f"Bearer {other_token}"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_demo_customer_can_reset_portal_report_without_removing_seeded_tickets(workspace):
    from app.seed.customer_dispatch import seed_dispatch
    session, config, data, actors = workspace
    seed_dispatch(session, config.model_copy(update={"demo_seed_enabled": True}))
    seeded_ticket_ids = set(session.scalars(select(Ticket.id)))
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: config
    app.dependency_overrides[get_portal_embedder] = lambda: LocalDeterministicEmbeddingProvider()
    app.dependency_overrides[get_portal_chat_provider] = lambda: LocalDeterministicChatProvider()
    token, _ = create_access_token(actors[0].id, "customer")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with TestClient(app) as client:
            first = client.post("/portal/me/chat/messages", json={
                "message": "No internet on every device using Ethernet, I want to make a report.",
            }, headers=headers)
            assert first.status_code == 200
            created = client.post("/portal/me/chat/messages", json={
                "message": "LOS is red", "answer_choice": "red_los",
                "conversation_id": first.json()["conversation_id"],
            }, headers=headers)
            assert created.status_code == 200
            report = created.json()["report"]
            assert report is not None
            staff_ticket_id = session.get(CustomerTroubleTicket, report["ticket_id"]).ticket_id
            assert staff_ticket_id is not None

            reset = client.delete("/portal/me/reset-data", headers=headers)
            assert reset.status_code == 200 and reset.json()["deleted_reports"] == 1
            assert session.scalar(select(CustomerTroubleTicket).where(CustomerTroubleTicket.reference == f"DEMO-{report['reference']}")) is None
            assert session.get(Ticket, staff_ticket_id) is None
            assert set(session.scalars(select(Ticket.id))) == seeded_ticket_ids
    finally:
        app.dependency_overrides.clear()


def test_customer_answers_do_not_describe_the_system_as_a_demo(workspace):
    result = ask(workspace)
    assert "demo" not in result.answer.lower() and "prototype" not in result.answer.lower()
    assert "cannot confirm" in result.answer
    assert result.is_demo is True


def test_old_history_and_retries_remove_demo_wording_without_changing_storage(workspace):
    from app.services.customer_chat import get_history
    session, _, _, actors = workspace
    request_id = uuid4()
    first = ask(workspace, request_id=request_id)
    turn = session.scalar(select(CustomerChatTurn).where(CustomerChatTurn.conversation_id == first.conversation_id))
    original = {**turn.response, "answer": "This is a local demo, not a live Unifi network check. " + first.answer}
    turn.response = original
    session.commit()
    assert get_history(session, actors[0], first.conversation_id).turns[0].response.answer == first.answer
    assert ask(workspace, request_id=request_id).answer == first.answer
    session.refresh(turn)
    assert turn.response == original
