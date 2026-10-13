"""Explainable reasoning for agent tool calls.

The hosted planner is a small model, so the reasoning shown to the technician
is derived deterministically from the same telemetry summarize.py reads
(router CPU, memory and temperature, client RSSI, radio channels, plan) plus
the retrieved knowledge-base sections. Each tool call gets: what was observed,
why this tool, the expected outcome, the risk, and how to roll it back. The
plan also records the alternatives the agent considered and rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import tool_executor
from app.domain.models import Customer, NetworkDevice, Router, Ticket

CPU_LIMIT = 80
MEMORY_LIMIT = 80
TEMPERATURE_LIMIT = 75
WEAK_RSSI = -75
_INFRA = {"router", "root", "gateway", "onu", "ont", "olt"}


@dataclass(frozen=True)
class ClientSignal:
    device_id: str
    name: str
    mac: str | None
    band: str | None
    rssi: int | None
    access_point: bool = False


@dataclass(frozen=True)
class Signals:
    alarm: str | None = None
    cpu: int | None = None
    memory: int | None = None
    temperature: int | None = None
    rx_power: float | None = None
    usage_gb: float | None = None
    channel_24: int | None = None
    channel_5: int | None = None
    congestion_24: int | None = None
    best_24: int | None = None
    best_24_utilization: int | None = None
    clients: tuple[ClientSignal, ...] = ()
    router_name: str | None = None

    @property
    def weak(self) -> list[ClientSignal]:
        return [client for client in self.clients if client.rssi is not None and client.rssi < WEAK_RSSI]

    @property
    def steerable(self) -> list[ClientSignal]:
        return [client for client in self.clients if client.band == "2.4" and client.rssi is not None and client.rssi >= -67
                and not client.access_point]

    @property
    def overloaded(self) -> bool:
        return (self.cpu or 0) >= CPU_LIMIT or (self.memory or 0) >= MEMORY_LIMIT


@dataclass
class ToolReasoning:
    observations: list[str] = field(default_factory=list)
    why: str = ""
    expected: str = ""
    risk: str = ""
    rollback: str = ""
    sources: list[str] = field(default_factory=list)
    trigger: str = "evidence"

    def as_dict(self) -> dict:
        return {
            "observations": self.observations,
            "why": self.why,
            "expected": self.expected,
            "risk": self.risk,
            "rollback": self.rollback,
            "sources": self.sources,
            "trigger": self.trigger,
        }


def _band(device: NetworkDevice) -> str | None:
    link = (device.link_type or "").lower()
    return "5" if link.startswith("5") else "2.4" if link.startswith("2") else None


def collect_signals(session: Session, ticket_id: str, router_device: NetworkDevice | None) -> Signals:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        return Signals()
    devices = list(session.scalars(select(NetworkDevice).where(NetworkDevice.customer_id == ticket.customer_id)).all())
    clients = tuple(
        ClientSignal(device.id, device.friendly_name or device.name, device.mac_address, _band(device), device.rssi,
                     (device.cloud_device_type or "").lower() == "access point")
        for device in devices
        if device.device_type.strip().lower() not in _INFRA
    )
    customer = session.get(Customer, ticket.customer_id)
    router = session.scalars(select(Router).where(Router.login_id == customer.customer_ref)).first() if customer else None
    congestion = best = best_util = None
    if router_device is not None:
        wireless = tuple(device for device in devices if device.id != router_device.id and device.device_type.strip().lower() not in _INFRA)
        scan = tool_executor.spectrum(router_device, tool_executor.SimContext(clients=wireless))["2.4"]
        congestion, best, best_util = scan["current_utilization"], scan["recommended"], scan["recommended_utilization"]
    return Signals(
        alarm=_alarm(ticket.summary),
        cpu=router.cpu_usage_pct if router else None,
        memory=router.memory_usage_pct if router else None,
        temperature=router.cpu_temperature_c if router else None,
        rx_power=float(router.rx_power_dbm) if router and router.rx_power_dbm is not None else None,
        usage_gb=float(router.monthly_usage_gb) if router and router.monthly_usage_gb is not None else None,
        channel_24=router_device.channel_2_4ghz if router_device else None,
        channel_5=router_device.channel_5ghz if router_device else None,
        congestion_24=congestion,
        best_24=best,
        best_24_utilization=best_util,
        clients=clients,
        router_name=router_device.name if router_device else None,
    )


def _alarm(summary: str | None) -> str | None:
    if not summary:
        return None
    for token in summary.replace(",", " ").split():
        if token.isupper() and "_" in token:
            return token.strip(".:;")
    return None


def observations(signals: Signals) -> list[dict]:
    """Ordered observe/flag lines the plan reasoning trace starts from."""
    lines: list[dict] = []
    if signals.alarm:
        lines.append({"kind": "observe", "text": f"Ticket alarm {signals.alarm}", "level": "warn"})
    if signals.cpu is not None:
        lines.append({"kind": "observe", "text": f"Router CPU {signals.cpu}% (limit {CPU_LIMIT}%)",
                      "level": "warn" if signals.cpu >= CPU_LIMIT else "ok"})
    if signals.memory is not None:
        lines.append({"kind": "observe", "text": f"Router memory {signals.memory}% (limit {MEMORY_LIMIT}%)",
                      "level": "warn" if signals.memory >= MEMORY_LIMIT else "ok"})
    if signals.temperature is not None and signals.temperature >= TEMPERATURE_LIMIT:
        lines.append({"kind": "observe", "text": f"Router temperature {signals.temperature}°C", "level": "warn"})
    if signals.clients:
        weak = signals.weak
        lines.append({"kind": "observe",
                      "text": f"{len(signals.clients)} clients, {len(weak)} below {WEAK_RSSI} dBm"
                      + (f" (worst {min(weak, key=lambda c: c.rssi or 0).name} {min(c.rssi or 0 for c in weak)} dBm)" if weak else ""),
                      "level": "warn" if weak else "ok"})
    if signals.congestion_24 is not None and signals.channel_24:
        lines.append({"kind": "observe",
                      "text": f"2.4 GHz channel {signals.channel_24} is {signals.congestion_24}% busy; channel {signals.best_24} is {signals.best_24_utilization}%",
                      "level": "warn" if signals.congestion_24 >= 60 else "ok"})
    if signals.rx_power is not None and signals.rx_power < -27:
        lines.append({"kind": "observe", "text": f"Optical RX {signals.rx_power} dBm is below -27 dBm", "level": "warn"})
    return lines


def signal_candidates(signals: Signals) -> list[dict]:
    """Tool calls the telemetry itself argues for, before any model output."""
    entries: list[dict] = []
    if signals.overloaded:
        entries.append({"tool_name": "reboot_router", "parameters": {}, "confidence": 0.88,
                        "rationale": f"CPU {signals.cpu}% / memory {signals.memory}% exceed the {CPU_LIMIT}% limit; a reboot clears the stuck processes."})
    if signals.memory is not None and signals.memory >= MEMORY_LIMIT and signals.alarm and "REBOOT" in signals.alarm:
        entries.append({"tool_name": "upgrade_firmware", "parameters": {}, "confidence": 0.7,
                        "rationale": "A reboot loop with high memory points to a firmware memory leak; the new image fixes it if reboots keep recurring."})
    if signals.congestion_24 is not None and signals.congestion_24 >= 55:
        entries.append({"tool_name": "optimize_wifi_radio", "parameters": {}, "confidence": 0.8,
                        "rationale": f"Channel {signals.channel_24} is {signals.congestion_24}% busy; moving to {signals.best_24} ({signals.best_24_utilization}%) cuts interference."})
    if signals.weak:
        entries.append({"tool_name": "client_signal_survey", "parameters": {}, "confidence": 0.78,
                        "rationale": f"{len(signals.weak)} client(s) are below {WEAK_RSSI} dBm; the survey shows where mesh coverage is needed."})
    steer = signals.steerable
    if steer:
        target = max(steer, key=lambda client: client.rssi or -100)
        if target.mac:
            entries.append({"tool_name": "steer_client_band", "parameters": {"client_mac": target.mac.lower(), "target_band": "5"},
                            "confidence": 0.7,
                            "rationale": f"{target.name} has a strong {target.rssi} dBm signal on crowded 2.4 GHz; 5 GHz gives it roughly twice the link rate."})
    if not entries:
        entries.append({"tool_name": "trace_service_path", "parameters": {}, "confidence": 0.65,
                        "rationale": "No resource or coverage fault stands out; a hop-by-hop trace localises where latency starts."})
    return entries


_EXPECTED = {
    "reboot_router": ("CPU and memory drop back under the limit; clients reconnect within about a minute.",
                      "All clients lose connectivity for 1-2 minutes.", "None needed; the router returns to its saved configuration."),
    "reboot_ont": ("The PON link re-ranges and the LOS alarm clears.", "Fibre service drops for about 2 minutes.", "None needed."),
    "refresh_ont_registration": ("The ONU re-registers and the PON link is restored.", "Brief service interruption.", "None needed."),
    "reset_optical_port": ("Receive power re-baselines and optical alarms clear.", "Service drops while the port resets.", "Escalate to field fibre team if levels stay low."),
    "set_wifi_channel": ("Clients on that band see less interference and higher throughput.", "Clients on the band reconnect for a few seconds.",
                         "Set the previous channel again."),
    "optimize_wifi_radio": ("Both radios move to their cleanest channels and weak clients gain signal.", "Wireless clients reconnect for a few seconds.",
                            "Restore the previous channels and power from the recorded diff."),
    "set_wifi_ssid": ("The network broadcasts the new name.", "Every client must rejoin with the new SSID.", "Rename back to the previous SSID."),
    "update_config": ("The radio runs with the new bounded setting.", "Radio reloads briefly.", "Re-apply the snapshot taken before the change."),
    "steer_client_band": ("The client roams to the faster band and its link rate rises.", "The client re-associates for about a second.",
                          "Steer it back to the original band."),
    "set_qos_priority": ("The client's traffic is queued ahead of bulk traffic.", "Other clients may see slightly lower priority.",
                         "Set the priority back to normal."),
    "upgrade_firmware": ("The memory-leak fix stops the reboot loop.", "The router is offline for 3-5 minutes during the flash.",
                         "Boot the previous image kept on partition A."),
    "flush_dns_cache": ("Stale DNS answers are cleared.", "First lookups are slightly slower.", "None needed."),
    "restart_service": ("The affected service session is re-established.", "That service drops briefly.", "None needed."),
    "block_client": ("The client can no longer use the network.", "Blocks a customer device; confirm with the subscriber.", "Remove the MAC filter."),
    "set_dhcp_reservation": ("The client always receives the reserved address.", "A conflicting lease would be moved.", "Delete the reservation."),
}

_READ_ONLY_EXPECTED = {
    "get_device_status": "Live status plus CPU, memory, temperature and optical counters.",
    "list_connected_clients": "Every associated client with band and signal.",
    "run_speed_test": "Download, upload and latency from the router WAN.",
    "run_optical_diagnostics": "Receive power and LOS state on the optical link.",
    "wifi_spectrum_scan": "Busy percentage per channel on both bands and the cleanest channel.",
    "trace_service_path": "Latency and loss on each hop, and which hop is the bottleneck.",
    "client_signal_survey": "Each client's signal grade and whether it needs mesh or band steering.",
}


def explain(tool_name: str, kind: str, parameters: dict, rationale: str, signals: Signals,
            sources: list[str], trigger: str) -> ToolReasoning:
    observed = [line["text"] for line in observations(signals) if line["level"] == "warn"][:4]
    if kind == "read_only":
        expected = _READ_ONLY_EXPECTED.get(tool_name, "A read-only result; nothing on the device changes.")
        return ToolReasoning(observations=observed, why=rationale, expected=expected,
                             risk="None: read-only, nothing on the device changes.", rollback="Not needed.",
                             sources=sources, trigger=trigger)
    expected, risk, rollback = _EXPECTED.get(tool_name, ("The device applies the change.", "Changes device state.", "Revert the change."))
    if tool_name == "reboot_router" and signals.cpu is not None:
        expected = f"CPU {signals.cpu}% and memory {signals.memory}% drop back under {CPU_LIMIT}%; clients reconnect within about a minute."
    if tool_name == "set_wifi_channel":
        rollback = f"Move back to channel {signals.channel_24 if parameters.get('band') == '2.4' else signals.channel_5}."
    return ToolReasoning(observations=observed, why=rationale, expected=expected, risk=risk, rollback=rollback,
                         sources=sources, trigger=trigger)


_REJECT_REASONS = {
    "run_speed_test": "measures throughput but cannot explain or fix the fault",
    "reboot_router": "router CPU and memory are within limits, so a reboot would only disconnect clients",
    "optimize_wifi_radio": "the current channel is not congested",
    "client_signal_survey": "no client is below the weak-signal threshold",
    "upgrade_firmware": "no reboot loop or memory leak pattern",
    "reboot_ont": "no optical alarm on this ticket",
    "run_optical_diagnostics": "optical receive power is healthy",
}


def rejected_alternatives(chosen: set[str], signals: Signals) -> list[dict]:
    """Two or three tools the agent considered and why they were not chosen."""
    candidates = []
    if "run_speed_test" not in chosen:
        candidates.append("run_speed_test")
    if "reboot_router" not in chosen and not signals.overloaded:
        candidates.append("reboot_router")
    if "optimize_wifi_radio" not in chosen and (signals.congestion_24 or 0) < 55:
        candidates.append("optimize_wifi_radio")
    if "client_signal_survey" not in chosen and not signals.weak:
        candidates.append("client_signal_survey")
    if "run_optical_diagnostics" not in chosen and (signals.rx_power is None or signals.rx_power >= -27):
        candidates.append("run_optical_diagnostics")
    return [{"tool_name": name, "reason": _REJECT_REASONS[name]} for name in candidates[:3]]
