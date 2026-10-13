from types import SimpleNamespace

from app.ai.ports import ChunkMatch
from app.ai.summarization import build_customer_facts, summarize_answer, summarize_matches


def _device(**overrides):
    values = dict(
        login_id="ticksew19@unifi",
        device_type="STA",
        link_type="5 GHz",
        manufacturer="Oppo",
        brand="Oppo",
        friendly_name="OPPO-A57",
        name="Oppo phone",
        rssi=-83,
        rx_rate=1111,
        tx_rate=267,
        platform="Android",
        cloud_device_type="Gateway",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _router():
    return SimpleNamespace(
        login_id="ticksew19@unifi",
        serial_number="CWTCB90BE9D3",
        manufacturer="SKYWORTH",
        model="AX1800",
        cpu_usage_pct=44,
        cpu_temperature_c=45,
        memory_usage_pct=56,
        monthly_usage_gb=312.4,
        rx_power_dbm=-22.6,
    )


def _devices():
    return [
        _device(device_type="Root", cloud_device_type="Access Point", rssi=None, friendly_name="Root"),
        _device(rssi=-83),
        _device(rssi=-85),
        _device(rssi=-44),
    ]


class _Provider:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, messages, *, temperature=0.0):
        return self.reply


def _match():
    return ChunkMatch(
        chunk_id="kb-wifi-1",
        document_id="kb-wifi",
        document_title="WiFi Coverage Guide",
        section="Coverage",
        source_type="HSI",
        content="Weak signal is fixed by adding a mesh node.",
        score=0.9,
    )


def test_customer_facts_reuse_summarizer_recommendations():
    facts = build_customer_facts("ticksew19@unifi", _devices(), [_router()])

    assert "Customer login ID: ticksew19@unifi" in facts
    assert "Recommended action: add a mesh node" in facts
    assert "outdated model, replacement recommended" in facts


def test_summarize_matches_applies_summarizer_actions_and_guardrails():
    provider = _Provider(
        "PROBLEM: Two wireless devices have weak signal.\n"
        "SUGGESTION: Add a mesh node or repeater to extend coverage.\n"
        "ACTIONS:"
    )

    summary = summarize_matches(
        login_id="ticksew19@unifi",
        devices=_devices(),
        routers=[_router()],
        matches=[_match()],
        provider=provider,
    )

    assert summary.problem
    assert summary.actions == ["mesh"]
    assert summary.product_recommendation
    assert "mesh" in summary.product_recommendation.lower()


def test_summarize_matches_falls_back_to_summarizer_facts_for_echo_providers():
    summary = summarize_matches(
        login_id="ticksew19@unifi",
        devices=_devices(),
        routers=[_router()],
        matches=[_match()],
        provider=_Provider('{"echo": true}'),
    )

    assert "weak WiFi signal" in summary.problem
    assert "outdated model" in summary.problem
    assert summary.actions == ["mesh"]
    assert "mesh node" in summary.solution.lower()
    assert "replace the outdated router" in summary.solution.lower()


def test_no_remediation_text_is_replaced_by_summarizer_actions():
    summary = summarize_answer(
        login_id="ticksew19@unifi",
        devices=_devices(),
        routers=[_router()],
        answer="CPE reboot loop on the root router.",
        solution="No specific remediation steps found for CPE_REBOOT_LOOP in the provided evidence.",
        product_recommendation=None,
    )

    assert "No specific remediation" not in (summary.solution or "")
    assert "mesh node" in summary.solution.lower()
    assert summary.actions == ["mesh"]
    assert "mesh" in (summary.product_recommendation or "").lower()


def test_summarize_answer_keeps_summarizer_action_sync():
    strong = [_device(rssi=-45), _device(rssi=-50)]
    summary = summarize_answer(
        login_id="ticksew19@unifi",
        devices=strong,
        routers=[_router()],
        answer="Restart the router to clear high CPU usage.",
        solution="Reboot the router.",
        product_recommendation=None,
        actions=["reboot"],
    )

    assert summary.actions == ["reboot"]
    assert summary.problem == "Restart the router to clear high CPU usage."
    assert summary.solution == "Reboot the router. Replace the outdated router with a current model."
