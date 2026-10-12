import json
from datetime import timedelta
from uuid import uuid4

import pytest
import httpx
from pydantic import ValidationError
from sqlalchemy import func, select

from app.domain.customer_chat_schemas import CustomerChatRequest
from app.domain.models import (
    AuditEvent, Customer, CustomerAccount, CustomerChatTurn, CustomerRouterAction,
    CustomerRouterState, DeviceMeasurement, NetworkDevice, ServiceMeasurement, User,
)
from app.config import Settings
from app.services.customer_chat import CustomerChatConflictError, visible_response, get_history
from app.services.customer_router_actions import RouterActionError, confirm
from app.seed.customer_router import stage_vlan_mismatch
from test_customer_chat import workspace, ask, NOW  # noqa: F401


def config(workspace, **changes):
    return workspace[1].model_copy(update={"customer_chat_mode": "agent",
        "customer_router_simulation_enabled": True, "app_environment": "test", **changes})


class ScriptedAgent:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.contexts = []

    def complete(self, messages, **kwargs):
        if "CUSTOMER_AGENT_V1" not in messages[0].content:
            return json.dumps({"intent": "slow_internet", "connection": "unknown", "device_scope": "unknown", "near_router": "unknown"})
        self.contexts.append(json.loads(messages[-1].content))
        return json.dumps(next(self.decisions))


def test_model_observes_tools_and_can_choose_different_question_order(workspace):
    provider = ScriptedAgent([{"tool": "get_diagnostics"}, {"tool": "search_guidance"},
        {"tool": "ask_question", "arguments": {"question_id": "connection"}}])
    result = ask(workspace, provider=provider, settings=config(workspace, customer_chat_provider="hosted"))
    assert result.orchestration == "agent_hosted"
    assert result.follow_up.id == "connection"  # Guided default asks device_scope first.
    assert [step.tool for step in result.agent_trace] == ["get_diagnostics", "search_guidance", "ask_question"]
    assert "get_diagnostics" in provider.contexts[1]["tool_observations"]
    assert "search_guidance" in provider.contexts[2]["tool_observations"]
    encoded = json.dumps(provider.contexts)
    customer = workspace[0].get(Customer, workspace[0].get(CustomerAccount, workspace[3][0].id).customer_id)
    assert customer.address not in encoded and customer.id not in encoded


@pytest.mark.parametrize("decision", [
    {"tool": "execute_confirmed_action"},
    {"tool": "propose_vlan_restore", "arguments": {"service_type": "HSI", "vlan_id": 999}},
    {"tool": "propose_reboot", "arguments": {"device_id": "other"}},
    {"tool": "ask_question", "arguments": {"question_id": "made_up"}},
    {"tool": "run_sql", "arguments": {"sql": "DELETE FROM customers"}},
])
def test_unapproved_model_decisions_fall_back_without_writes(workspace, decision):
    provider = ScriptedAgent([{"tool": "get_diagnostics"}, decision])
    result = ask(workspace, provider=provider, settings=config(workspace, customer_chat_provider="hosted"))
    assert result.orchestration == "agent_fallback" and result.follow_up.id == "device_scope"
    assert workspace[0].scalar(select(func.count()).select_from(CustomerRouterAction)) == 0


def test_repeated_tool_and_step_budget_stop_the_agent(workspace):
    for decisions in ([{"tool": "get_diagnostics"}] * 2,
        [{"tool": "get_diagnostics"}, {"tool": "get_router_action_status"}, {"tool": "search_guidance"}]):
        result = ask(workspace, "Please restart my router", provider=ScriptedAgent(decisions),
            settings=config(workspace, customer_chat_provider="hosted", customer_agent_max_steps=3))
        assert result.orchestration == "agent_fallback"
        assert result.agent_trace[-1].outcome == "fallback"
        ask(workspace, "Cancel action", settings=config(workspace), conversation_id=result.conversation_id,
            answer_choice="cancel_router_action", action_id=result.router_action.id)


def test_reboot_requires_specific_confirmation_and_does_not_mutate_telemetry(workspace):
    session, _, _, actors = workspace
    readings = [(row.id, row.quality, row.observed_at, row.operational_status) for row in session.scalars(select(DeviceMeasurement))]
    before = {row.id: (row.status, dict(row.details)) for row in session.scalars(select(NetworkDevice))}
    first = ask(workspace, "Please restart my router", settings=config(workspace))
    assert first.status == "action_confirmation" and first.router_action.simulation
    assert session.scalar(select(func.count()).select_from(CustomerRouterState)) == 0
    pending = ask(workspace, "yes", conversation_id=first.conversation_id, settings=config(workspace))
    assert pending.status == "action_confirmation"  # Free text is not confirmation.
    request_id = uuid4()
    done = ask(workspace, "Confirm action", conversation_id=first.conversation_id,
        answer_choice="confirm_router_action", action_id=first.router_action.id,
        request_id=request_id, settings=config(workspace))
    assert done.status == "action_completed" and done.follow_up.id == "router_action_check"
    assert not done.no_actions_taken
    assert session.scalar(select(CustomerRouterState.reboot_count)) == 1
    retry = ask(workspace, "Confirm action", conversation_id=first.conversation_id,
        answer_choice="confirm_router_action", action_id=first.router_action.id,
        request_id=request_id, settings=config(workspace))
    assert retry.router_action.status == "succeeded"
    assert session.scalar(select(CustomerRouterState.reboot_count)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == "customer_router_action_executed")) == 1
    assert before == {row.id: (row.status, dict(row.details)) for row in session.scalars(select(NetworkDevice))}
    assert readings == [(row.id, row.quality, row.observed_at, row.operational_status) for row in session.scalars(select(DeviceMeasurement))]
    history = get_history(session, actors[0], first.conversation_id)
    assert history.turns[0].response.answer == first.answer
    assert history.turns[0].response.follow_up is None
    public = visible_response(done).model_dump()
    assert "agent_trace" not in public and "router_action_details" not in public and "submitted_action_id" not in public
    resolved = ask(workspace, "It's working now", conversation_id=first.conversation_id, answer_choice="resolved", settings=config(workspace))
    assert resolved.status == "resolved" and not resolved.report


def test_vlan_restore_uses_backend_profile_and_records_actual_simulated_change(workspace):
    session = workspace[0]
    before = [(row.id, row.vlan_id) for row in session.scalars(select(ServiceMeasurement))]
    stage_vlan_mismatch(session, config(workspace, demo_seed_enabled=True), customer_ref="SYN-00042-0002", service_type="IPTV", vlan_id=601)
    first = ask(workspace, "Please reconfigure my IPTV VLAN", settings=config(workspace))
    assert first.router_action.kind == "restore_vlan" and first.router_action.label == "Restore IPTV VLAN configuration"
    done = ask(workspace, "Confirm action", settings=config(workspace), conversation_id=first.conversation_id,
        answer_choice="confirm_router_action", action_id=first.router_action.id)
    assert done.router_action_details["before"]["service_vlans"]["IPTV"] == 601
    assert done.router_action_details["after"]["service_vlans"]["IPTV"] == 600
    assert before == [(row.id, row.vlan_id) for row in session.scalars(select(ServiceMeasurement))]
    assert session.scalar(select(CustomerRouterState)).service_vlans["HSI"] == 500


def test_cancel_expiry_and_cross_account_are_rejected_safely(workspace):
    session, _, _, actors = workspace
    first = ask(workspace, "Restart my router", settings=config(workspace))
    with pytest.raises(RouterActionError):
        confirm(session, actors[1], config(workspace), first.conversation_id, first.router_action.id, now=NOW)
    with pytest.raises(RouterActionError, match="expired"):
        confirm(session, actors[0], config(workspace), first.conversation_id, first.router_action.id, now=NOW + timedelta(minutes=11))
    cancelled = ask(workspace, "Cancel action", settings=config(workspace), conversation_id=first.conversation_id,
        answer_choice="cancel_router_action", action_id=first.router_action.id)
    assert cancelled.status == "action_cancelled"
    assert session.scalar(select(func.count()).select_from(CustomerRouterState)) == 0
    with pytest.raises(CustomerChatConflictError):
        ask(workspace, "Confirm action", settings=config(workspace), conversation_id=first.conversation_id,
            answer_choice="confirm_router_action", action_id=first.router_action.id)


@pytest.mark.parametrize("restriction", ["disabled", "real_user", "real_customer", "non_synthetic"])
def test_actions_unavailable_outside_fictional_opt_in_scope(workspace, restriction):
    session, _, _, actors = workspace
    settings = config(workspace)
    link = session.get(CustomerAccount, actors[0].id)
    if restriction == "disabled":
        settings = config(workspace, customer_router_simulation_enabled=False)
    elif restriction == "real_user":
        session.get(User, actors[0].id).is_demo = False
    elif restriction == "real_customer":
        session.get(Customer, link.customer_id).is_demo = False
    else:
        device = session.scalar(select(NetworkDevice).where(NetworkDevice.customer_id == link.customer_id, NetworkDevice.device_type == "router"))
        device.details = {**device.details, "is_synthetic": False}
    session.commit()
    result = ask(workspace, "Restart my router", settings=settings)
    assert result.router_action is None
    assert session.scalar(select(func.count()).select_from(CustomerRouterAction)) == 0


def test_fibre_fault_prevents_reboot_and_vlan_proposals(workspace):
    session, _, data, actors = workspace
    session.get(CustomerAccount, actors[0].id).customer_id = data["tables"]["customers"][4]["id"]
    session.commit()
    result = ask(workspace, "No internet, please restart my router", settings=config(workspace))
    assert result.router_action is None


def test_no_improvement_after_action_can_create_trouble_ticket(workspace):
    first = ask(workspace, "My internet is slow, please reboot my router", settings=config(workspace))
    ask(workspace, "Confirm action", settings=config(workspace), conversation_id=first.conversation_id,
        answer_choice="confirm_router_action", action_id=first.router_action.id)
    failed = ask(workspace, "Still not working", settings=config(workspace), conversation_id=first.conversation_id,
        answer_choice="still_not_working")
    assert failed.follow_up.id == "submit_report"
    report = ask(workspace, "Arrange technician review", settings=config(workspace), conversation_id=first.conversation_id,
        answer_choice="submit_report")
    assert report.status == "report_created" and report.report


def test_confirmation_schema_and_production_gate():
    with pytest.raises(ValidationError):
        CustomerChatRequest(message="Confirm", answer_choice="confirm_router_action")
    with pytest.raises(ValidationError):
        CustomerChatRequest(message="Hello", action_id=uuid4())
    with pytest.raises(ValidationError):
        Settings(customer_router_simulation_enabled=True, app_environment="production")


def test_customer_can_report_improvement_in_free_text(workspace):
    first = ask(workspace, "Restart my router", settings=config(workspace))
    ask(workspace, "Confirm action", settings=config(workspace), conversation_id=first.conversation_id,
        answer_choice="confirm_router_action", action_id=first.router_action.id)
    result = ask(workspace, "It's working now", settings=config(workspace), conversation_id=first.conversation_id)
    assert result.status == "resolved" and result.workflow.self_help == "resolved"


def test_hosted_provider_sends_explicit_budget_and_rejects_empty_content():
    from app.ai.ports import ChatMessage
    from app.integrations.model_provider import HostedChatCompletionProvider
    def handler(request):
        assert json.loads(request.content)["max_tokens"] == 1024
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = HostedChatCompletionProvider(base_url="https://model.test.invalid/v1", api_key="fictional-test-key",
            model="test", client=client, max_output_tokens=1024)
        with pytest.raises(RuntimeError, match="empty or unsupported"):
            provider.complete([ChatMessage(role="user", content="Fictional complaint")])
