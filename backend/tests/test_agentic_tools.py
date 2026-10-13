from types import SimpleNamespace

from app.ai import tool_executor
from app.domain.models import NetworkDevice
from app.services import tool_reasoning
from app.services.agent_tools import explicit_tool_calls


def _router(**overrides) -> NetworkDevice:
    values = dict(id="r1", name="Root", device_ref="ROOT", device_type="Root", status="online",
                  channel_2_4ghz=11, channel_5ghz=44, details={}, customer_id="c1")
    values.update(overrides)
    return NetworkDevice(**values)


def _client(device_id: str, link: str, rssi: int, mac: str, name: str, **extra) -> NetworkDevice:
    return NetworkDevice(id=device_id, name=name, device_ref=name, device_type="STA", status="online", link_type=link,
                         rssi=rssi, tx_rate=300, mac_address=mac, details={}, customer_id="c1", **extra)


CLIENTS = (
    _client("a", "2.4 GHz", -60, "aa:aa:aa:aa:aa:aa", "Kitchen Phone", platform="iOS"),
    _client("b", "5 GHz", -82, "bb:bb:bb:bb:bb:bb", "Bedroom TV"),
)
TELEMETRY = SimpleNamespace(cpu_usage_pct=86, memory_usage_pct=85, cpu_temperature_c=60, rx_power_dbm=-19.0)


def test_spectrum_scan_recommends_a_cleaner_non_overlapping_channel():
    result = tool_executor.wifi_spectrum_scan(_router(), tool_executor.SimContext(clients=CLIENTS))
    two = result.data["bands"]["2.4"]
    assert two["recommended"] in (1, 6) and two["recommended"] != two["current"]
    assert two["recommended_utilization"] < two["current_utilization"]
    assert [step["label"] for step in result.trace][:2] == ["Put radio in monitor mode", "Sweep 2.4 GHz"]


def test_reboot_releases_cpu_and_memory():
    result = tool_executor.reboot_router(_router(), tool_executor.SimContext(clients=CLIENTS, router=TELEMETRY))
    assert result.router_updates["cpu_usage_pct"] < 80
    assert result.router_updates["memory_usage_pct"] < 80
    assert result.data["kind"] == "diff"


def test_trace_service_path_starts_at_the_weakest_client():
    result = tool_executor.trace_service_path(_router(), tool_executor.SimContext(clients=CLIENTS, router=TELEMETRY))
    hops = result.data["hops"]
    assert hops[0]["device_id"] == "b"
    assert hops[-1]["role"] == "internet"
    assert result.data["bottleneck"] == "Root"


def test_steering_moves_the_client_to_5ghz():
    result = tool_executor.steer_client_band(_router(), "aa:aa:aa:aa:aa:aa", "5", tool_executor.SimContext(clients=CLIENTS))
    assert result.client_updates["a"]["link_type"] == "5 GHz"
    assert tool_executor.steer_client_band(_router(), "cc:cc:cc:cc:cc:cc", "5", tool_executor.SimContext(clients=CLIENTS)).succeeded is False


def test_explicit_requests_map_to_the_new_tools():
    names = lambda question: [entry["tool_name"] for entry in explicit_tool_calls(question, _router(), list(CLIENTS))]
    assert names("optimise the wifi") == ["optimize_wifi_radio"]
    assert names("why is the internet lagging?") == ["trace_service_path"]
    assert names("upgrade the router firmware") == ["upgrade_firmware"]
    steer = explicit_tool_calls("move the iphone to 5ghz", _router(), list(CLIENTS))
    assert steer[0]["tool_name"] == "steer_client_band"
    assert steer[0]["parameters"] == {"client_mac": "aa:aa:aa:aa:aa:aa", "target_band": "5"}
    channel = explicit_tool_calls("configure the router to a less congested channel", _router(), list(CLIENTS))[0]
    assert channel["tool_name"] == "set_wifi_channel" and channel["parameters"]["channel"] != 11


def test_telemetry_ranks_a_reboot_first_for_an_overloaded_router():
    signals = tool_reasoning.Signals(alarm="CPE_REBOOT_LOOP", cpu=86, memory=85, clients=(
        tool_reasoning.ClientSignal("b", "Bedroom TV", "bb:bb:bb:bb:bb:bb", "5", -82),
    ))
    names = [entry["tool_name"] for entry in tool_reasoning.signal_candidates(signals)]
    assert names[:2] == ["reboot_router", "upgrade_firmware"]
    assert "client_signal_survey" in names
    lines = tool_reasoning.observations(signals)
    assert any(line["level"] == "warn" and "CPU 86%" in line["text"] for line in lines)
    reasoning = tool_reasoning.explain("reboot_router", "stateful", {}, "why", signals, ["KB › CPE reboot loop"], "telemetry")
    assert "86%" in reasoning.expected and reasoning.rollback


def test_rejected_alternatives_explain_skipped_tools():
    healthy = tool_reasoning.Signals(cpu=30, memory=40)
    rejected = {item["tool_name"] for item in tool_reasoning.rejected_alternatives({"trace_service_path"}, healthy)}
    assert "reboot_router" in rejected
