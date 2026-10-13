import json

import pytest

from app.ai.ports import ChunkMatch
from app.auth.dependencies import AuthenticatedUser
from app.integrations.model_provider import LocalDeterministicChatProvider
from app.services import agent_tools
from app.services.agent_tools import AgentToolProposalError, _parse_call, plan_agent_tools, propose_agent_tool


def test_parse_call_accepts_bare_json():
    assert _parse_call('{"tool_name": "reboot_router", "arguments": {}}') == {
        "tool_name": "reboot_router",
        "arguments": {},
    }


def test_parse_call_extracts_json_from_markdown_fence():
    raw = (
        "Here is the call:\n"
        '```json\n{"tool_name": "get_device_status", "arguments": {"device_id": "d1"}}\n```'
    )

    call = _parse_call(raw)

    assert call["tool_name"] == "get_device_status"
    assert call["arguments"] == {"device_id": "d1"}


def test_parse_call_rejects_unstructured_text():
    with pytest.raises(AgentToolProposalError):
        _parse_call("I cannot help with that.")


class _StaticProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, messages, *, temperature: float = 0.0) -> str:
        return json.dumps(self.payload)


class _NullEmbedder:
    dimension = 8

    def embed_documents(self, texts):
        return [[0.0] * self.dimension for _ in texts]

    def embed_query(self, text):
        return [0.0] * self.dimension


def _chunk(chunk_id: str = "chunk-1") -> ChunkMatch:
    return ChunkMatch(
        chunk_id=chunk_id,
        document_id="doc-1",
        document_title="Optical procedure",
        section="Checks",
        source_type="procedure",
        content="Confirm LOS, then re-register the ONU before dispatch.",
        score=0.9,
    )


@pytest.fixture
def grounded(monkeypatch):
    monkeypatch.setattr(agent_tools.retrieval, "retrieve_for_ticket", lambda *a, **k: [_chunk()])


def _actor(workspace, key: str, role: str) -> AuthenticatedUser:
    user = workspace[key]
    return AuthenticatedUser(id=user.id, email=user.email, role=role)


def test_plan_returns_ranked_validated_suggestions(db_session, tool_workspace, grounded):
    provider = _StaticProvider(
        {
            "summary": "Start with diagnostics.",
            "suggestions": [
                {"tool_name": "run_optical_diagnostics", "rationale": "Read LOS first.", "confidence": 0.9, "parameters": {}},
                {"tool_name": "reboot_ont", "rationale": "Power-cycle if still down.", "confidence": 0.7, "parameters": {}},
                {"tool_name": "drop_database", "rationale": "nope", "confidence": 1.0, "parameters": {}},
            ],
        }
    )
    plan = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "ONU is offline with LOS",
        tool_workspace["onu"].id,
        embedder=_NullEmbedder(),
        provider=provider,
    )
    names = [suggestion.tool_name for suggestion in plan.suggestions]
    assert names == ["run_optical_diagnostics", "reboot_ont"]
    assert all(suggestion.evidence == ["chunk-1"] for suggestion in plan.suggestions)
    assert plan.summary == "Start with diagnostics."


def test_plan_filters_wrong_device_type(db_session, tool_workspace, grounded):
    provider = _StaticProvider(
        {"summary": "x", "suggestions": [{"tool_name": "reboot_router", "rationale": "r", "parameters": {}}]}
    )
    plan = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "reboot the ONU",
        tool_workspace["onu"].id,
        embedder=_NullEmbedder(),
        provider=provider,
    )
    assert "reboot_router" not in [suggestion.tool_name for suggestion in plan.suggestions]


def test_forced_propose_uses_selected_tool(db_session, tool_workspace, grounded):
    record = propose_agent_tool(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "reboot the router",
        tool_workspace["router"].id,
        embedder=_NullEmbedder(),
        provider=_StaticProvider({"tool_name": "none", "arguments": {}}),
        tool_name="reboot_router",
        parameters={},
    )
    assert record.tool_name == "reboot_router"
    assert record.status == "proposed"


def test_forced_propose_rejects_unpermitted_tool(db_session, tool_workspace, grounded):
    with pytest.raises(AgentToolProposalError):
        propose_agent_tool(
            db_session,
            tool_workspace["ticket"].id,
            _actor(tool_workspace, "technician_a", "technician"),
            "reboot the router",
            tool_workspace["router"].id,
            embedder=_NullEmbedder(),
            provider=_StaticProvider({"tool_name": "none", "arguments": {}}),
            tool_name="reboot_router",
            parameters={"settings": {"wifi_channel": 99}},
        )


def test_plan_selects_the_device_the_request_is_about(db_session, tool_workspace, grounded):
    provider = LocalDeterministicChatProvider()

    optical = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "the ONU is offline with LOS",
        None,
        embedder=_NullEmbedder(),
        provider=provider,
    )
    assert optical.device_id == tool_workspace["onu"].id

    wifi = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "configure the router to change the wifi channel to 44",
        None,
        embedder=_NullEmbedder(),
        provider=provider,
    )
    assert wifi.device_id == tool_workspace["router"].id


def test_plan_uses_retrieved_optical_evidence_for_generic_question(db_session, tool_workspace, monkeypatch):
    monkeypatch.setattr(
        agent_tools.retrieval,
        "retrieve_for_ticket",
        lambda *a, **k: [ChunkMatch(
            chunk_id="chunk-los",
            document_id="doc-1",
            document_title="ONU Offline Field Checks",
            section="LOS checks",
            source_type="procedure",
            content="Check MY-ONT-001 for LOS and receive power before dispatch.",
            score=0.9,
        )],
    )
    plan = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "What should I check first?",
        None,
        embedder=_NullEmbedder(),
        provider=LocalDeterministicChatProvider(),
    )
    assert plan.device_id == tool_workspace["onu"].id
    assert plan.suggestions[0].tool_name == "run_optical_diagnostics"


def test_local_plan_honors_the_requested_channel_and_band(db_session, tool_workspace, grounded):
    plan = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "configure the router to change the channel to 44",
        tool_workspace["router"].id,
        embedder=_NullEmbedder(),
        provider=LocalDeterministicChatProvider(),
    )
    top = plan.suggestions[0]
    assert top.tool_name == "set_wifi_channel"
    assert top.parameters == {"band": "5", "channel": 44}
    assert top.steps
    assert any("44" in step for step in top.steps)


def test_local_plan_returns_a_useful_suggestion_for_a_router(db_session, tool_workspace, grounded):
    plan = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "configure the router to change the wifi channel to 44",
        tool_workspace["router"].id,
        embedder=_NullEmbedder(),
        provider=LocalDeterministicChatProvider(),
    )
    assert [s.tool_name for s in plan.suggestions]


def test_incomplete_configuration_request_does_not_invent_a_change(db_session, tool_workspace, grounded):
    plan = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "config for me",
        tool_workspace["router"].id,
        embedder=_NullEmbedder(),
        provider=LocalDeterministicChatProvider(),
    )

    assert plan.suggestions == []
    assert "No device action was taken" in plan.summary


def test_explicit_configure_request_is_planned_without_a_value(db_session, tool_workspace, grounded):
    plan = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "configure the router to a less congested wifi channel",
        tool_workspace["router"].id,
        embedder=_NullEmbedder(),
        provider=_StaticProvider({"summary": "nothing", "suggestions": []}),
    )
    top = plan.suggestions[0]
    assert top.tool_name == "set_wifi_channel"
    assert top.parameters["channel"] in (1, 6, 11)


def test_explicit_requests_do_not_need_retrieved_evidence(db_session, tool_workspace, monkeypatch):
    monkeypatch.setattr(agent_tools.retrieval, "retrieve_for_ticket", lambda *a, **k: [])
    plan = plan_agent_tools(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace, "technician_a", "technician"),
        "rename the wifi to 'Kairos Home' and reboot the router",
        tool_workspace["router"].id,
        embedder=_NullEmbedder(),
        provider=_StaticProvider({"summary": "x", "suggestions": []}),
    )
    names = [suggestion.tool_name for suggestion in plan.suggestions]
    assert names[:2] == ["set_wifi_ssid", "reboot_router"]
    assert plan.suggestions[0].parameters == {"ssid_2g": "Kairos Home", "ssid_5g": "Kairos Home"}


def test_detect_action_intent():
    assert agent_tools.detect_action_intent("configure the router to channel 6") == "configuration"
    assert agent_tools.detect_action_intent("please reboot the router") == "stateful"
    assert agent_tools.detect_action_intent("check the router status") == "diagnostic"
    assert agent_tools.detect_action_intent("Summarize this ticket") is None
