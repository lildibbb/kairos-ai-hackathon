"""Simulated tool execution.

Each executor mutates the in-database simulated device state and returns a
result the caller can persist and audit. They never touch real hardware. The
dispatch table keeps the service layer free of per-tool branching.

Every result carries a ``trace`` (the ordered steps the simulated device went
through, with durations the UI replays as a live stream) and ``data`` (a
structured payload such as a channel scan or hop list, keyed by ``kind``).
Values are derived deterministically from the device so a replay is stable.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.domain.models import NetworkDevice

TraceStep = dict[str, Any]


@dataclass(frozen=True)
class SimContext:
    """Read-only surroundings of the target: its Wi-Fi clients and router telemetry."""

    clients: tuple[NetworkDevice, ...] = ()
    router: Any | None = None


@dataclass(frozen=True)
class SimulationResult:
    succeeded: bool
    message: str
    device_status: str | None = None
    details_updates: dict = field(default_factory=dict)
    trace: list[TraceStep] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    # Column updates for the routers telemetry row (cpu_usage_pct, ...).
    router_updates: dict = field(default_factory=dict)
    # Per-client column updates keyed by device id (link_type, rssi, ...).
    client_updates: dict[str, dict] = field(default_factory=dict)


def _step(label: str, detail: str = "", ms: int = 450, status: str = "ok") -> TraceStep:
    return {"label": label, "detail": detail, "ms": ms, "status": status}


def _seed(device: NetworkDevice, salt: str) -> int:
    return int(hashlib.sha256(f"{device.id}:{salt}".encode()).hexdigest()[:8], 16)


def _band(client: NetworkDevice) -> str | None:
    link = (client.link_type or "").lower()
    if link.startswith("5"):
        return "5"
    if link.startswith("2"):
        return "2.4"
    return None


def _client_name(client: NetworkDevice) -> str:
    return client.friendly_name or client.name or client.device_ref


def _quality(rssi: int | None) -> str:
    if rssi is None:
        return "wired"
    if rssi >= -55:
        return "excellent"
    if rssi >= -67:
        return "good"
    if rssi >= -75:
        return "fair"
    return "weak"


def _wireless(ctx: SimContext) -> list[NetworkDevice]:
    return [client for client in ctx.clients if _band(client) is not None]


def get_device_status(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    router = ctx.router
    metrics = []
    if router is not None:
        metrics = [
            {"label": "CPU", "value": router.cpu_usage_pct, "unit": "%", "warn": (router.cpu_usage_pct or 0) >= 80},
            {"label": "Memory", "value": router.memory_usage_pct, "unit": "%", "warn": (router.memory_usage_pct or 0) >= 80},
            {"label": "Temperature", "value": router.cpu_temperature_c, "unit": "°C", "warn": (router.cpu_temperature_c or 0) >= 75},
            {"label": "Optical RX", "value": float(router.rx_power_dbm) if router.rx_power_dbm is not None else None, "unit": "dBm",
             "warn": router.rx_power_dbm is not None and float(router.rx_power_dbm) < -27},
        ]
    flagged = [item["label"] for item in metrics if item["warn"]]
    return SimulationResult(
        succeeded=True,
        message=f"{device.name} reports status '{device.status}'"
        + (f"; attention: {', '.join(flagged)}." if flagged else "."),
        trace=[
            _step("Open management session", f"TR-069 connection request to {device.device_ref}", 380),
            _step("Read device parameters", "InternetGatewayDevice.DeviceInfo.*", 520),
            _step("Read resource counters", "CPU, memory, temperature, optical RX", 460, "warn" if flagged else "ok"),
        ],
        data={"kind": "status", "status": device.status, "metrics": metrics,
              "clients": len(ctx.clients)},
    )


def list_connected_clients(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    rows = [
        {"device_id": client.id, "name": _client_name(client), "band": _band(client) or "wired",
         "rssi": client.rssi, "quality": _quality(client.rssi), "mac": client.mac_address}
        for client in ctx.clients
    ]
    if not rows:
        refs = [str(ref) for ref in (device.details.get("connected_clients", []) or [])]
        message = (f"{device.name} reports {len(refs)} connected client(s): {', '.join(refs)}." if refs
                   else f"{device.name} reports no simulated clients attached.")
    else:
        message = f"{device.name} reports {len(rows)} connected client(s)."
    return SimulationResult(
        succeeded=True,
        message=message,
        trace=[
            _step("Query association table", "2.4 GHz and 5 GHz radios", 420),
            _step("Query DHCP leases", f"{len(rows)} active lease(s)", 380),
        ],
        data={"kind": "clients", "clients": rows},
    )


def run_speed_test(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    download = float(device.details.get("download_mbps", 480.0) or 480.0)
    upload = float(device.details.get("upload_mbps", 95.0) or 95.0)
    latency = 4 + _seed(device, "lat") % 9
    return SimulationResult(
        succeeded=True,
        message=f"{device.name} throughput test: {download:.1f} Mbps down / {upload:.1f} Mbps up.",
        trace=[
            _step("Select test server", "Kuala Lumpur speed-test node", 400),
            _step("Measure latency", f"{latency} ms idle", 500),
            _step("Download test", f"{download:.0f} Mbps", 900),
            _step("Upload test", f"{upload:.0f} Mbps", 700),
        ],
        data={"kind": "speed", "download_mbps": download, "upload_mbps": upload, "latency_ms": latency},
    )


def run_optical_diagnostics(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    rx = device.details.get("rx_power_db", "unknown")
    los = device.details.get("los_status", "unknown")
    return SimulationResult(
        succeeded=True,
        message=f"{device.name} optical read: rx_power_db={rx}, los_status={los}.",
        trace=[
            _step("Query OLT port", "GPON optical module", 450),
            _step("Read receive power", f"{rx} dBm", 420),
            _step("Read LOS state", str(los), 360, "warn" if str(los).upper() not in ("OK", "UNKNOWN") else "ok"),
        ],
        data={"kind": "optical", "rx_power_db": rx, "los_status": los},
    )


def reboot_router(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    router = ctx.router
    wireless = len(ctx.clients)
    trace = [
        _step("Send reboot command", f"TR-069 Reboot RPC to {device.device_ref}", 500),
        _step("Router went offline", "Heartbeat lost; Wi-Fi clients disconnected", 700, "warn"),
        _step("Boot sequence", "Bootloader → kernel → network stack", 900),
        _step("WAN session re-established", "PPPoE up, public IP assigned", 600),
        _step("Clients reassociated", f"{wireless} client(s) reconnected", 500),
    ]
    diff = []
    router_updates: dict = {}
    if router is not None:
        cpu_before, mem_before = router.cpu_usage_pct, router.memory_usage_pct
        if cpu_before is not None:
            router_updates["cpu_usage_pct"] = max(9, round(cpu_before * 0.28))
            diff.append({"field": "CPU", "before": f"{cpu_before}%", "after": f"{router_updates['cpu_usage_pct']}%"})
        if mem_before is not None:
            router_updates["memory_usage_pct"] = max(24, round(mem_before * 0.45))
            diff.append({"field": "Memory", "before": f"{mem_before}%", "after": f"{router_updates['memory_usage_pct']}%"})
        if diff:
            trace.append(_step("Resources released", ", ".join(f"{d['field']} {d['before']} → {d['after']}" for d in diff), 400))
    diff.insert(0, {"field": "Status", "before": "rebooting", "after": "online"})
    return SimulationResult(
        succeeded=True,
        message=f"{device.name} rebooted and is back online.",
        device_status="online",
        trace=trace,
        data={"kind": "diff", "changes": diff},
        router_updates=router_updates,
    )


def reboot_ont(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    return SimulationResult(
        succeeded=True,
        message=f"{device.name} power-cycled and re-established the PON link.",
        device_status="online",
        details_updates={"los_status": "OK"},
        trace=[
            _step("Send power-cycle", "OMCI reboot to ONU", 500),
            _step("PON link down", "Ranging lost", 700, "warn"),
            _step("ONU ranging", "Registered with OLT", 800),
        ],
        data={"kind": "diff", "changes": [{"field": "LOS", "before": str(device.details.get("los_status", "?")), "after": "OK"}]},
    )


def refresh_ont_registration(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    return SimulationResult(
        succeeded=True,
        message=f"{device.name} re-registered with the OLT.",
        device_status="online",
        details_updates={"los_status": "OK", "registered": True},
        trace=[_step("Deregister ONU", "OLT port", 500), _step("Re-register ONU", "Serial number authenticated", 800)],
        data={"kind": "diff", "changes": [{"field": "Registration", "before": "stale", "after": "registered"}]},
    )


def reset_optical_port(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    baseline = device.details.get("baseline_rx_power_db", -21.4)
    return SimulationResult(
        succeeded=True,
        message=f"{device.name} optical port reset; receive power re-baselined to {baseline} dBm.",
        details_updates={"rx_power_db": baseline, "los_status": "OK"},
        trace=[_step("Disable optical port", "", 500, "warn"), _step("Enable optical port", "", 600),
               _step("Re-baseline RX power", f"{baseline} dBm", 500)],
        data={"kind": "diff", "changes": [{"field": "RX power", "before": str(device.details.get("rx_power_db", "?")), "after": f"{baseline} dBm"}]},
    )


def update_config(device: NetworkDevice, settings: dict[str, int], ctx: SimContext = SimContext()) -> SimulationResult:
    applied = ", ".join(f"{key}={value}" for key, value in sorted(settings.items()))
    previous = dict((device.details or {}).get("settings", {}) or {})
    return SimulationResult(
        succeeded=True,
        message=f"Applied configuration on {device.name}: {applied}.",
        details_updates={"settings": {**previous, **settings}},
        trace=[_step("Snapshot running configuration", "Rollback point saved", 400),
               _step("Apply settings", applied, 700), _step("Commit and reload radio", "", 600)],
        data={"kind": "diff", "changes": [
            {"field": key, "before": str(previous.get(key, "default")), "after": str(value)} for key, value in sorted(settings.items())
        ]},
    )


def set_wifi_ssid(device: NetworkDevice, ssid_2g: str | None, ssid_5g: str | None, ctx: SimContext = SimContext()) -> SimulationResult:
    updates: dict[str, object] = {}
    changed: list[str] = []
    diff = []
    if ssid_2g is not None:
        updates["ssid_2g"] = ssid_2g
        changed.append(f"2.4G={ssid_2g}")
        diff.append({"field": "SSID 2.4 GHz", "before": device.ssid_2_4ghz or "—", "after": ssid_2g})
    if ssid_5g is not None:
        updates["ssid_5g"] = ssid_5g
        changed.append(f"5G={ssid_5g}")
        diff.append({"field": "SSID 5 GHz", "before": device.ssid_5ghz or "—", "after": ssid_5g})
    return SimulationResult(
        succeeded=True,
        message=f"Renamed Wi-Fi network on {device.name}: {', '.join(changed)}.",
        details_updates=updates,
        trace=[_step("Snapshot wireless configuration", "", 400), _step("Write new SSID", ", ".join(changed), 600),
               _step("Restart beacons", "Clients must rejoin the new network", 700, "warn")],
        data={"kind": "diff", "changes": diff},
    )


def set_wifi_channel(device: NetworkDevice, band: str, channel: int, ctx: SimContext = SimContext()) -> SimulationResult:
    key = "channel_2g" if band == "2.4" else "channel_5g"
    before = device.channel_2_4ghz if band == "2.4" else device.channel_5ghz
    affected = [client for client in _wireless(ctx) if _band(client) == band]
    return SimulationResult(
        succeeded=True,
        message=f"Moved {band} GHz radio on {device.name} to channel {channel}.",
        details_updates={key: channel},
        trace=[
            _step("Snapshot radio configuration", f"{band} GHz on channel {before or 'auto'}", 400),
            _step("Announce channel switch", "CSA beacons so clients follow", 600),
            _step("Retune radio", f"Channel {before or 'auto'} → {channel}", 700),
            _step("Clients rejoined", f"{len(affected)} client(s) on {band} GHz", 500),
        ],
        data={"kind": "diff", "changes": [{"field": f"{band} GHz channel", "before": str(before or "auto"), "after": str(channel)}],
              "affected_ids": [client.id for client in affected]},
    )


def flush_dns_cache(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    entries = 120 + _seed(device, "dns") % 400
    return SimulationResult(
        succeeded=True,
        message=f"Resolver cache flushed on {device.name}.",
        details_updates={"dns_cache": "flushed"},
        trace=[_step("Read resolver cache", f"{entries} cached records", 400), _step("Flush cache", "", 500),
               _step("Test resolution", "unifi.com.my → resolved in 18 ms", 500)],
        data={"kind": "diff", "changes": [{"field": "DNS cache", "before": f"{entries} records", "after": "empty"}]},
    )


def restart_service(device: NetworkDevice, service: str, ctx: SimContext = SimContext()) -> SimulationResult:
    return SimulationResult(
        succeeded=True,
        message=f"Restarted the {service.upper()} service stack on {device.name}.",
        details_updates={f"{service}_restarted": True},
        trace=[_step(f"Stop {service.upper()} stack", "", 500, "warn"), _step(f"Start {service.upper()} stack", "", 700),
               _step("Service health check", "Session up", 500)],
        data={"kind": "diff", "changes": [{"field": f"{service.upper()} service", "before": "degraded", "after": "restarted"}]},
    )


def block_client(device: NetworkDevice, client_mac: str, ctx: SimContext = SimContext()) -> SimulationResult:
    blocked = list(device.details.get("blocked_clients", []) or [])
    if client_mac not in blocked:
        blocked.append(client_mac)
    return SimulationResult(
        succeeded=True,
        message=f"Quarantined client {client_mac} on {device.name}.",
        details_updates={"blocked_clients": blocked},
        trace=[_step("Add MAC filter", client_mac, 500), _step("Deauthenticate client", "", 500, "warn")],
        data={"kind": "diff", "changes": [{"field": client_mac, "before": "allowed", "after": "blocked"}]},
    )


def set_dhcp_reservation(device: NetworkDevice, client_mac: str, ip_address: str, ctx: SimContext = SimContext()) -> SimulationResult:
    reservations = dict(device.details.get("dhcp_reservations", {}) or {})
    reservations[client_mac] = ip_address
    return SimulationResult(
        succeeded=True,
        message=f"Reserved {ip_address} for {client_mac} on {device.name}.",
        details_updates={"dhcp_reservations": reservations},
        trace=[_step("Check address pool", f"{ip_address} is free", 400), _step("Write reservation", "", 500)],
        data={"kind": "diff", "changes": [{"field": client_mac, "before": "dynamic", "after": ip_address}]},
    )


# --- Agentic tools -------------------------------------------------------------------------

_SCAN_CHANNELS = {"2.4": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], "5": [36, 40, 44, 48, 149, 153, 157, 161]}
_PRIMARY = {"2.4": (1, 6, 11), "5": (36, 40, 44, 48, 149, 153, 157, 161)}


def spectrum(device: NetworkDevice, ctx: SimContext = SimContext()) -> dict:
    """Deterministic per-channel utilisation; the current channel is shared with neighbours."""
    bands = {}
    for band, channels in _SCAN_CHANNELS.items():
        current = device.channel_2_4ghz if band == "2.4" else device.channel_5ghz
        own = len([client for client in ctx.clients if _band(client) == band])
        rows = []
        for channel in channels:
            noise = _seed(device, f"{band}:{channel}") % 100
            base = 18 + noise * 0.55 if band == "2.4" else 4 + noise * 0.3
            if current and abs(channel - current) <= (2 if band == "2.4" else 0):
                base += 30 if band == "2.4" else 22
            networks = 1 + (noise // 14 if band == "2.4" else noise // 30)
            rows.append({"channel": channel, "utilization": min(97, round(base + own * 2)), "networks": networks})
        eligible = [row for row in rows if row["channel"] in _PRIMARY[band] and row["channel"] != current]
        best = min(eligible, key=lambda row: row["utilization"])
        current_row = next((row for row in rows if row["channel"] == current), None)
        bands[band] = {"current": current, "current_utilization": current_row["utilization"] if current_row else None,
                       "recommended": best["channel"], "recommended_utilization": best["utilization"], "channels": rows}
    return bands


def wifi_spectrum_scan(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    bands = spectrum(device, ctx)
    neighbours = sum(row["networks"] for band in bands.values() for row in band["channels"])
    two, five = bands["2.4"], bands["5"]
    return SimulationResult(
        succeeded=True,
        message=(
            f"Scanned {len(two['channels']) + len(five['channels'])} channels on {device.name}: "
            f"2.4 GHz channel {two['current']} is {two['current_utilization']}% busy, channel {two['recommended']} is {two['recommended_utilization']}%; "
            f"5 GHz best is channel {five['recommended']} ({five['recommended_utilization']}%)."
        ),
        trace=[
            _step("Put radio in monitor mode", "Clients keep their association", 400),
            _step("Sweep 2.4 GHz", "Channels 1–13", 900),
            _step("Sweep 5 GHz", "UNII-1 and UNII-3", 800),
            _step("Classify neighbours", f"{neighbours} overlapping networks detected", 500,
                  "warn" if (two["current_utilization"] or 0) > 60 else "ok"),
            _step("Rank channels", f"2.4 GHz → {two['recommended']}, 5 GHz → {five['recommended']}", 400),
        ],
        data={"kind": "spectrum", "bands": bands},
    )


def trace_service_path(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    wireless = sorted(_wireless(ctx), key=lambda client: client.rssi if client.rssi is not None else 0)
    source = wireless[0] if wireless else None
    router = ctx.router
    rx = float(router.rx_power_dbm) if router is not None and router.rx_power_dbm is not None else -19.5
    wifi_ms = 2 if source is None or (source.rssi or -50) >= -60 else 9 if (source.rssi or -50) >= -72 else 24
    wifi_loss = 0 if wifi_ms < 9 else 1.2 if wifi_ms < 24 else 4.8
    cpu = (router.cpu_usage_pct or 0) if router is not None else 0
    router_ms = 1 if cpu < 70 else 6 if cpu < 85 else 14
    optical_ms = 1 if rx > -25 else 7
    hops = []
    if source is not None:
        hops.append({"name": _client_name(source), "role": "client", "device_id": source.id, "latency_ms": 0, "loss_pct": 0,
                     "status": "ok", "note": f"{_band(source)} GHz, {source.rssi} dBm"})
    hops += [
        {"name": device.name, "role": "Wi-Fi hop" if source else "router", "device_id": device.id, "latency_ms": wifi_ms + router_ms,
         "loss_pct": wifi_loss, "status": "warn" if wifi_ms + router_ms >= 9 else "ok",
         "note": f"Wi-Fi {wifi_ms} ms + router CPU {cpu}% adds {router_ms} ms"},
        {"name": "ONU / optical", "role": "access", "latency_ms": optical_ms, "loss_pct": 0, "status": "warn" if optical_ms > 3 else "ok",
         "note": f"RX {rx} dBm"},
        {"name": "OLT", "role": "access", "latency_ms": 1, "loss_pct": 0, "status": "ok", "note": "GPON port"},
        {"name": "BNG", "role": "core", "latency_ms": 2, "loss_pct": 0, "status": "ok", "note": "Subscriber session"},
        {"name": "Internet (1.1.1.1)", "role": "internet", "latency_ms": 3, "loss_pct": 0, "status": "ok", "note": "Peering KL-IX"},
    ]
    total = sum(hop["latency_ms"] for hop in hops)
    worst = max(hops, key=lambda hop: hop["latency_ms"])
    return SimulationResult(
        succeeded=True,
        message=f"End-to-end path {total} ms; the slowest hop is {worst['name']} ({worst['latency_ms']} ms, {worst['note']}).",
        trace=[_step(f"Probe {hop['name']}", f"{hop['latency_ms']} ms" + (f", {hop['loss_pct']}% loss" if hop["loss_pct"] else ""),
                     380, hop["status"]) for hop in hops],
        data={"kind": "path", "hops": hops, "total_ms": total, "bottleneck": worst["name"]},
    )


def client_signal_survey(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    rows = []
    for client in sorted(_wireless(ctx), key=lambda item: item.rssi if item.rssi is not None else 0):
        quality = _quality(client.rssi)
        band = _band(client)
        advice = None
        if quality == "weak":
            advice = "Out of range: add a mesh node near this device"
        elif band == "2.4" and quality in ("excellent", "good"):
            advice = "Strong signal on 2.4 GHz: steer to 5 GHz for more speed"
        elif quality == "fair":
            advice = "Borderline coverage"
        rows.append({"device_id": client.id, "name": _client_name(client), "mac": client.mac_address, "band": band,
                     "rssi": client.rssi, "rate_mbps": client.tx_rate, "quality": quality, "advice": advice})
    weak = [row for row in rows if row["quality"] == "weak"]
    steerable = [row for row in rows if row["advice"] and row["advice"].startswith("Strong")]
    return SimulationResult(
        succeeded=True,
        message=(f"Surveyed {len(rows)} wireless client(s): {len(weak)} weak, {len(steerable)} could move to 5 GHz."
                 if rows else f"{device.name} has no wireless clients to survey."),
        trace=[_step("Read per-station RSSI", f"{len(rows)} station(s)", 500),
               _step("Read PHY rates", "Negotiated TX/RX rates", 400),
               _step("Grade coverage", f"{len(weak)} weak client(s)", 400, "warn" if weak else "ok")],
        data={"kind": "survey", "clients": rows},
    )


def steer_client_band(device: NetworkDevice, client_mac: str, target_band: str, ctx: SimContext = SimContext()) -> SimulationResult:
    client = next((item for item in ctx.clients if (item.mac_address or "").lower() == client_mac), None)
    if client is None:
        return SimulationResult(succeeded=False, message=f"Client {client_mac} is not associated with {device.name}.",
                                trace=[_step("Look up client", client_mac, 400, "fail")])
    before_band = _band(client) or "wired"
    rssi_after = (client.rssi or -60) - (6 if target_band == "5" else -4)
    rate_after = round((client.tx_rate or 150) * (2.3 if target_band == "5" else 0.5))
    channel = device.channel_5ghz if target_band == "5" else device.channel_2_4ghz
    label = "5 GHz" if target_band == "5" else "2.4 GHz"
    updates = {"link_type": label, "rssi": rssi_after, "tx_rate": rate_after}
    return SimulationResult(
        succeeded=True,
        message=f"Steered {_client_name(client)} from {before_band} GHz to {label}; link rate {client.tx_rate} → {rate_after} Mbps.",
        trace=[
            _step("Send BSS transition request", f"802.11v to {client_mac}", 500),
            _step("Client roamed", f"Associated on {label} channel {channel}", 800),
            _step("Measure new link", f"{rssi_after} dBm, {rate_after} Mbps", 500),
        ],
        data={"kind": "diff", "changes": [
            {"field": "Band", "before": f"{before_band} GHz", "after": label},
            {"field": "Signal", "before": f"{client.rssi} dBm", "after": f"{rssi_after} dBm"},
            {"field": "Link rate", "before": f"{client.tx_rate} Mbps", "after": f"{rate_after} Mbps"},
        ], "affected_ids": [client.id]},
        client_updates={client.id: updates},
    )


def set_qos_priority(device: NetworkDevice, client_mac: str, priority: str, ctx: SimContext = SimContext()) -> SimulationResult:
    client = next((item for item in ctx.clients if (item.mac_address or "").lower() == client_mac), None)
    rules = dict(device.details.get("qos_rules", {}) or {})
    before = rules.get(client_mac, "normal")
    rules[client_mac] = priority
    name = _client_name(client) if client else client_mac
    return SimulationResult(
        succeeded=True,
        message=f"Set {priority} traffic priority for {name} on {device.name}.",
        details_updates={"qos_rules": rules},
        trace=[_step("Classify client traffic", f"{name} ({client_mac})", 400),
               _step("Write WMM / DSCP rule", f"{before} → {priority}", 600),
               _step("Reload traffic shaper", "Queues rebuilt", 500)],
        data={"kind": "diff", "changes": [{"field": f"{name} priority", "before": before, "after": priority}],
              "affected_ids": [client.id] if client else []},
    )


def optimize_wifi_radio(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    bands = spectrum(device, ctx)
    two, five = bands["2.4"], bands["5"]
    weak = [client for client in _wireless(ctx) if _quality(client.rssi) == "weak"]
    power = 23 if weak else 20
    previous_power = ((device.details or {}).get("settings", {}) or {}).get("tx_power_dbm", 17)
    settings = {**((device.details or {}).get("settings", {}) or {}), "tx_power_dbm": power}
    return SimulationResult(
        succeeded=True,
        message=(f"Optimised Wi-Fi on {device.name}: 2.4 GHz {two['current']} → {two['recommended']}, "
                 f"5 GHz {five['current']} → {five['recommended']}, transmit power {power} dBm."),
        details_updates={"channel_2g": two["recommended"], "channel_5g": five["recommended"], "settings": settings},
        trace=[
            _step("Spectrum scan", "26 channels across both bands", 900),
            _step("Score channels", f"2.4 GHz {two['current_utilization']}% → {two['recommended_utilization']}% busy", 500),
            _step("Retune 2.4 GHz", f"Channel {two['current']} → {two['recommended']}", 600),
            _step("Retune 5 GHz", f"Channel {five['current']} → {five['recommended']}", 600),
            _step("Adjust transmit power", f"{previous_power} → {power} dBm" + (" for weak clients" if weak else ""), 500),
            _step("Clients rejoined", f"{len(_wireless(ctx))} wireless client(s)", 500),
        ],
        data={"kind": "diff", "bands": bands, "changes": [
            {"field": "2.4 GHz channel", "before": str(two["current"]), "after": str(two["recommended"])},
            {"field": "5 GHz channel", "before": str(five["current"]), "after": str(five["recommended"])},
            {"field": "Transmit power", "before": f"{previous_power} dBm", "after": f"{power} dBm"},
        ], "affected_ids": [client.id for client in _wireless(ctx)]},
    )


_FIRMWARE_LATEST = "3.2.1"


def upgrade_firmware(device: NetworkDevice, ctx: SimContext = SimContext()) -> SimulationResult:
    current = str((device.details or {}).get("firmware_version") or "2.8.4")
    if current == _FIRMWARE_LATEST:
        return SimulationResult(succeeded=True, message=f"{device.name} already runs firmware {current}.",
                                trace=[_step("Check firmware", f"{current} is current", 400)],
                                data={"kind": "diff", "changes": []})
    router = ctx.router
    router_updates = {}
    changes = [{"field": "Firmware", "before": current, "after": _FIRMWARE_LATEST}]
    if router is not None and router.memory_usage_pct is not None:
        router_updates["memory_usage_pct"] = max(22, round(router.memory_usage_pct * 0.5))
        changes.append({"field": "Memory", "before": f"{router.memory_usage_pct}%", "after": f"{router_updates['memory_usage_pct']}%"})
    return SimulationResult(
        succeeded=True,
        message=f"Upgraded {device.name} firmware {current} → {_FIRMWARE_LATEST}; the memory-leak fix is active.",
        device_status="online",
        details_updates={"firmware_version": _FIRMWARE_LATEST},
        trace=[
            _step("Download image", f"v{_FIRMWARE_LATEST} (38.2 MB)", 900),
            _step("Verify signature", "SHA-256 and vendor signature OK", 500),
            _step("Write standby partition", "Partition B, previous image kept for rollback", 1000),
            _step("Reboot into new image", "Router offline", 900, "warn"),
            _step("Post-upgrade health", "WAN up, radios up", 500),
        ],
        data={"kind": "diff", "changes": changes},
        router_updates=router_updates,
    )


Executor = Callable[..., SimulationResult]

EXECUTORS: dict[str, Executor] = {
    "get_device_status": get_device_status,
    "list_connected_clients": list_connected_clients,
    "run_speed_test": run_speed_test,
    "run_optical_diagnostics": run_optical_diagnostics,
    "reboot_router": reboot_router,
    "reboot_ont": reboot_ont,
    "refresh_ont_registration": refresh_ont_registration,
    "reset_optical_port": reset_optical_port,
    "update_config": update_config,
    "set_wifi_ssid": set_wifi_ssid,
    "set_wifi_channel": set_wifi_channel,
    "flush_dns_cache": flush_dns_cache,
    "restart_service": restart_service,
    "block_client": block_client,
    "set_dhcp_reservation": set_dhcp_reservation,
    "wifi_spectrum_scan": wifi_spectrum_scan,
    "trace_service_path": trace_service_path,
    "client_signal_survey": client_signal_survey,
    "steer_client_band": steer_client_band,
    "set_qos_priority": set_qos_priority,
    "optimize_wifi_radio": optimize_wifi_radio,
    "upgrade_firmware": upgrade_firmware,
}


def run(tool_name: str, device: NetworkDevice, params, ctx: SimContext | None = None) -> SimulationResult:
    """Dispatch a tool to its simulator using validated parameters."""
    executor = EXECUTORS.get(tool_name)
    if executor is None:
        raise KeyError(tool_name)
    ctx = ctx or SimContext()
    if tool_name == "update_config":
        return executor(device, params.settings, ctx)
    if tool_name == "set_wifi_ssid":
        return executor(device, params.ssid_2g, params.ssid_5g, ctx)
    if tool_name == "set_wifi_channel":
        return executor(device, params.band, params.channel, ctx)
    if tool_name == "restart_service":
        return executor(device, params.service, ctx)
    if tool_name == "block_client":
        return executor(device, params.client_mac, ctx)
    if tool_name == "set_dhcp_reservation":
        return executor(device, params.client_mac, params.ip_address, ctx)
    if tool_name == "steer_client_band":
        return executor(device, params.client_mac, params.target_band, ctx)
    if tool_name == "set_qos_priority":
        return executor(device, params.client_mac, params.priority, ctx)
    return executor(device, ctx)
