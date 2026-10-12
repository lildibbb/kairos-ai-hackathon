import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.domain.models import Customer, CustomerAccount, CustomerChatTurn, CustomerTroubleTicket
from app.services.customer_chat import get_history, visible_response
from app.services.customer_response import reported_checks, troubleshooting_feedback
from test_customer_chat import workspace, ask  # noqa: F401


class ConversationalProvider:
    def __init__(self, reply, *, facts=None, interpretation=None):
        self.reply = reply
        self.facts = facts or ["approved_next_step"]
        self.interpretation = interpretation
        self.contexts = []

    def complete(self, messages, **kwargs):
        context = json.loads(messages[-1].content)
        if "CUSTOMER_RESPONSE_V1" in messages[0].content:
            self.contexts.append(context)
            if isinstance(self.reply, Exception):
                raise self.reply
            return json.dumps({"reply": self.reply, "used_facts": self.facts})
        if "CUSTOMER_AGENT_V1" in messages[0].content:
            if "get_diagnostics" not in context["tool_observations"]:
                return json.dumps({"tool": "get_diagnostics"})
            return json.dumps(context["suggested_next_step"])
        return json.dumps(self.interpretation or context["previous_reported_symptoms"] or {
            "intent": "slow_internet", "connection": "unknown", "device_scope": "unknown", "near_router": "unknown"})


def hosted(workspace, **updates):
    return workspace[1].model_copy(update={"customer_chat_provider": "hosted", **updates})


@pytest.mark.parametrize("text,outcome", [
    ("I don't think it is working after changing device, what do you think is the issue?", "failed"),
    ("I tried another device and the internet is still slow", "failed"),
    ("It isn't working yet", "failed"),
    ("It doesn't improve closer to the router", "failed"),
    ("The issue is not resolved", "failed"),
    ("It is working now, thanks for helping!", "resolved"),
    ("The problem has been resolved", "resolved"),
    ("I tried the cable but I am not sure yet", "unknown"),
    ("It improves near the router", "unknown"),
    ("It looks better but the problem is still there", "failed"),
    ("Masih tak boleh selepas tukar peranti", "failed"),
])
def test_feedback_handles_natural_replies_and_negation(text, outcome):
    assert troubleshooting_feedback(text) == outcome


def test_attempts_are_not_assumed_from_instructions_or_negation():
    assert reported_checks("Should I try another device?") == []
    assert reported_checks("I haven't tried another device") == []
    assert reported_checks("I tried another device using Ethernet") == ["another_device", "ethernet"]


def test_negated_near_router_comparison_does_not_trigger_mesh_advice(workspace):
    first = ask(workspace, "Slow Wi-Fi on every device")
    result = ask(workspace, "It doesn't improve closer to the router", conversation_id=first.conversation_id)
    assert result.reported.near_router == "same"
    assert result.assessment.category != "coverage"
    assert not result.assessment.sales_categories


def test_screenshot_message_advances_without_repeating_checks_or_creating_unapproved_ticket(workspace):
    session = workspace[0]
    first = ask(workspace, "Slow internet on every device using Ethernet")
    count = session.scalar(select(func.count()).select_from(CustomerTroubleTicket))
    failed = ask(workspace, "I don't think it is working after changing device, what do you think is the issue?",
        conversation_id=first.conversation_id)
    assert failed.workflow.self_help == "failed"
    assert "another_device" in failed.workflow.checks_tried
    assert failed.follow_up.id == "submit_report"
    assert "compare another device" not in failed.answer
    assert not failed.report
    assert session.scalar(select(func.count()).select_from(CustomerTroubleTicket)) == count


def test_llm_response_uses_context_and_survives_retry_and_history(workspace):
    first = ask(workspace, "Slow internet on every device using Ethernet")
    reply = "Thanks for trying another device. That suggests it may not be limited to the first device, but the exact cause is still unconfirmed. Further investigation by a technician is the next step."
    provider = ConversationalProvider(reply, facts=["persistent_issue", "customer_attempts"])
    request_id = uuid4()
    payload = dict(conversation_id=first.conversation_id, request_id=request_id,
        settings=hosted(workspace, customer_chat_mode="agent"), provider=provider)
    message = "I don't think it is working after changing device, what do you think is the issue?"
    result = ask(workspace, message, **payload)
    assert result.answer == reply and result.response_mode == "hosted"
    assert result.orchestration == "agent_hosted" and result.follow_up.id == "submit_report"
    context = provider.contexts[0]
    assert "another_device" in context["checks_already_tried"]
    assert context["recent_conversation"][0]["assistant"] == first.answer
    assert "persistent_issue" in context["approved_facts"]
    count = len(provider.contexts)
    assert ask(workspace, message, **payload).answer == reply
    assert len(provider.contexts) == count
    assert get_history(workspace[0], workspace[3][0], first.conversation_id).turns[-1].response.answer == reply
    assert "response_mode" not in visible_response(result).model_dump()


def test_generated_coverage_answer_is_not_replaced_on_reload(workspace):
    first = ask(workspace, "Slow Wi-Fi on every device")
    reply = "That improvement close to the router suggests coverage may be contributing in the original room. Try an open, central router position; if several rooms remain affected, a compatible mesh system may help."
    result = ask(workspace, "It improves", conversation_id=first.conversation_id,
        answer_choice="better_near_router", settings=hosted(workspace), provider=ConversationalProvider(reply))
    assert result.assessment.category == "coverage" and result.answer == reply
    assert result.response_mode == "hosted"
    assert get_history(workspace[0], workspace[3][0], first.conversation_id).turns[-1].response.answer == reply


@pytest.mark.parametrize("reply,facts", [
    ("Your router was rebooted and your appointment is booked.", ["approved_next_step"]),
    ("Your trouble ticket has been created for you.", ["approved_next_step"]),
    ("Penghala anda telah dimulakan semula dan janji temu telah disahkan.", ["approved_next_step"]),
    ("Anda mesti naik taraf kerana terlalu banyak peranti.", ["approved_next_step"]),
    ("Your signal is -79 dBm; the monthly price is RM 99.", ["approved_next_step"]),
    ("Click https://malicious.invalid to fix the problem.", ["approved_next_step"]),
    ("Your connection is healthy and the router is fine.", ["approved_next_step"]),
    ("There are too many devices, so you must upgrade.", ["approved_next_step"]),
    ("Factory-reset your router and disconnect the fibre cable.", ["approved_next_step"]),
    ("The problem is fixed; your internet is working again.", ["approved_next_step"]),
    ("The issue is coverage. You need to buy mesh.", ["approved_next_step"]),
    ("I can help narrow down the problem with you.", ["made_up_fact"]),
])
def test_unsupported_response_claims_fall_back_without_echo(workspace, reply, facts):
    result = ask(workspace, settings=hosted(workspace), provider=ConversationalProvider(reply, facts=facts))
    assert result.response_mode == "fallback"
    assert reply not in result.answer
    assert result.no_actions_taken


def test_response_failure_does_not_break_validated_workflow_or_leak_provider_error(workspace):
    result = ask(workspace, settings=hosted(workspace),
        provider=ConversationalProvider(httpx.ConnectError("private gateway details")))
    assert result.response_mode == "fallback" and result.follow_up.id == "device_scope"
    assert "private gateway details" not in result.model_dump_json()


def test_model_feedback_cannot_authorize_a_ticket_and_can_interpret_unlisted_phrasing(workspace):
    first = ask(workspace, "Slow internet on every device using Ethernet")
    provider = ConversationalProvider("Thanks for checking. We can continue with technician investigation.", interpretation={
        **first.reported.model_dump(), "check_outcome": "failed", "checks_tried": ["another_device"]})
    result = ask(workspace, "Switching laptops made absolutely no difference to it.",
        conversation_id=first.conversation_id, settings=hosted(workspace), provider=provider)
    assert result.workflow.self_help == "failed" and result.follow_up.id == "submit_report"
    assert not result.report and result.workflow.report_requested is False


def test_report_receipt_remains_authoritative_and_generated_intro_is_preserved(workspace):
    first = ask(workspace, "Slow internet on every device using Ethernet")
    failed = ask(workspace, "Still not working", conversation_id=first.conversation_id)
    intro = "Thanks for letting me know the checks did not help. Further investigation is appropriate here."
    result = ask(workspace, "Arrange technician review", conversation_id=first.conversation_id,
        answer_choice="submit_report", settings=hosted(workspace), provider=ConversationalProvider(intro))
    assert result.response_mode == "hosted" and result.report
    assert result.answer.startswith(intro) and result.report.reference.removeprefix("DEMO-") in result.answer
    history = get_history(workspace[0], workspace[3][0], first.conversation_id)
    assert history.turns[-1].response.answer == result.answer
    assert history.turns[-1].response.response_prefix == intro
    assert failed.follow_up.id == "submit_report"


def test_reply_context_excludes_account_identity_raw_measurements_and_credentials(workspace):
    provider = ConversationalProvider("I can help narrow this down with you. Let's start with which devices are affected.")
    result = ask(workspace, "Slow internet password=never-share-this contact test@example.invalid",
        settings=hosted(workspace), provider=provider)
    prompt = json.dumps(provider.contexts)
    customer = workspace[0].get(Customer, workspace[0].get(CustomerAccount, workspace[3][0].id).customer_id)
    assert customer.address not in prompt and customer.id not in prompt
    assert "never-share-this" not in prompt and "test@example.invalid" not in prompt
    assert "-79" not in prompt and "rssi_dbm" not in prompt
    assert result.response_mode == "hosted"


def test_plain_feedback_does_not_withdraw_prior_report_request(workspace):
    first = ask(workspace, "Slow internet on every device using Ethernet, please make a report")
    result = ask(workspace, "I don't think it is working after changing device",
        conversation_id=first.conversation_id)
    assert result.workflow.report_requested and result.report


def test_repeating_attempted_check_is_rejected(workspace):
    first = ask(workspace, "Slow internet on every device using Ethernet")
    result = ask(workspace, "I tried another device and it is still slow", conversation_id=first.conversation_id,
        settings=hosted(workspace), provider=ConversationalProvider("Try another device again and see if it helps."))
    assert result.response_mode == "fallback" and result.follow_up.id == "submit_report"


def test_grounded_ticket_offer_is_not_a_creation_claim(workspace):
    first = ask(workspace, "Slow internet on every device using Ethernet")
    reply = "Thanks for trying another device. Since the issue persists, I can create a trouble ticket for further technician investigation."
    result = ask(workspace, "I tried another device and it is still slow", conversation_id=first.conversation_id,
        settings=hosted(workspace), provider=ConversationalProvider(reply))
    assert result.response_mode == "hosted" and result.answer == reply
    assert result.follow_up.id == "submit_report" and not result.report


@pytest.mark.parametrize("initial", ["not JSON", RuntimeError("blank provider response")])
def test_response_repair_is_bounded_and_does_not_reexecute_tools(workspace, initial):
    class RepairingProvider(ConversationalProvider):
        attempts = 0

        def complete(self, messages, **kwargs):
            if "CUSTOMER_RESPONSE_V1" in messages[0].content:
                self.attempts += 1
                if self.attempts == 1:
                    if isinstance(initial, Exception):
                        raise initial
                    return initial
            return super().complete(messages, **kwargs)

    provider = RepairingProvider("I can help narrow down the problem. Let's start by checking which devices are affected.")
    result = ask(workspace, settings=hosted(workspace, customer_chat_mode="agent"), provider=provider)
    assert result.response_mode == "hosted" and provider.attempts == 2
    assert [step.tool for step in result.agent_trace] == ["get_diagnostics", "ask_question"]
    assert not result.report and not result.router_action
    assert workspace[0].scalar(select(func.count()).select_from(CustomerChatTurn)) == 1
