"""Evidence-backed support choices; these are conservative heuristics, not root causes."""

from app.domain.customer_chat_schemas import ChatWorkflow, CustomerCase, ReportedSymptoms
from app.domain.diagnostic_schemas import CustomerDiagnosticsRead


def _current(reading):
    return reading is not None and reading.freshness == "fresh" and reading.quality == "good"


def assess_case(data: CustomerDiagnosticsRead, symptoms: ReportedSymptoms, workflow: ChatWorkflow) -> CustomerCase:
    if workflow.router_lights == "red_los" or any(
        device.device_type == "ONU" and _current(device.latest_measurement) and device.latest_measurement.los_alarm
        for device in data.devices
    ):
        return CustomerCase(category="fibre_fault", evidence=["optical_loss_requires_investigation"])
    if symptoms.intent not in ("slow_internet", "disconnecting"):
        return CustomerCase()
    # A live WAN fault takes precedence over commercial recommendations.
    if any(device.device_type == "router" and _current(device.latest_measurement)
           and device.latest_measurement.wan_status in ("down", "offline", "disconnected") for device in data.devices):
        return CustomerCase(evidence=["current_wan_fault"])
    profile = next((service.speed_profile for service in data.services if service.service_type == "HSI"), None)
    if profile:
        for subscribed, applied in ((profile.subscribed_download_mbps, profile.provisioned_download_mbps),
                                    (profile.subscribed_upload_mbps, profile.provisioned_upload_mbps)):
            if subscribed is not None and applied is not None and subscribed != applied:
                return CustomerCase(category="profile_review", evidence=["stored_profile_mismatch"])
    if symptoms.connection == "wifi":
        congested = any(_current(row) and row.channel_utilization_pct >= 80 for row in data.radio_measurements)
        retries = any(_current(client.latest_measurement) and client.latest_measurement.connected
                      and (client.latest_measurement.retry_pct or 0) >= 20 for client in data.wifi_clients)
        if congested and retries and symptoms.near_router != "better":
            return CustomerCase(category="radio_congestion", evidence=["current_radio_utilization_and_retries"])
        if symptoms.near_router == "better":
            evidence = ["customer_reports_improvement_near_router"]
            if any(_current(client.latest_measurement) and client.latest_measurement.connected
                   and client.latest_measurement.rssi_dbm is not None and client.latest_measurement.rssi_dbm < -70
                   for client in data.wifi_clients):
                evidence.append("current_weak_signal")
            return CustomerCase(category="coverage", evidence=evidence, sales_categories=["mesh"])
    samples = []
    if profile and profile.subscribed_download_mbps and profile.subscribed_upload_mbps:
        # Require several distinct, non-overlapping traffic windows from one router.
        for row in sorted(data.wan_usage, key=lambda row: row.window_start):
            duration = (row.observed_at - row.window_start).total_seconds()
            if not _current(row) or not 60 <= duration <= 300 or row.active_devices < 2:
                continue
            if samples and (row.device_id != samples[0].device_id or row.window_start < samples[-1].observed_at):
                continue
            saturated = (row.download_mbps >= profile.subscribed_download_mbps * .9
                         or row.upload_mbps >= profile.subscribed_upload_mbps * .9)
            if saturated:
                samples.append(row)
    repeated_load = len(samples) >= 3 and symptoms.device_scope == "all"
    if repeated_load and workflow.traffic_pause == "better":
        return CustomerCase(category="bandwidth_capacity", evidence=["repeated_current_wan_saturation", "customer_reports_improvement_when_traffic_paused"], sales_categories=["plan"])
    return CustomerCase(evidence=["repeated_current_wan_saturation"] if repeated_load else [], capacity_check_suggested=repeated_load and workflow.traffic_pause == "untried")
