"""Explicit, credential-free customer diagnostic response fields."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, allow_inf_nan=False)

    observed_at: datetime
    ingested_at: datetime
    source: str
    quality: str
    age_seconds: float
    freshness: Literal["fresh", "stale", "invalid"]


class DeviceObservationRead(ObservationRead):
    operational_status: str
    management_reachable: bool | None
    wan_status: str | None
    uptime_seconds: int | None
    los_alarm: bool | None
    optical_rx_dbm: float | None
    optical_tx_dbm: float | None
    test_connection: str | None
    download_mbps: float | None
    upload_mbps: float | None
    latency_ms: float | None
    packet_loss_pct: float | None
    disconnect_count_24h: int | None
    disconnect_count_7d: int | None


class WifiObservationRead(ObservationRead):
    connected: bool
    rssi_dbm: float | None
    snr_db: float | None
    tx_link_mbps: float | None
    rx_link_mbps: float | None
    retry_pct: float | None


class ServiceObservationRead(ObservationRead):
    operational_status: str
    registration_status: str | None
    stream_status: str | None
    multicast_joined: bool | None
    jitter_ms: float | None
    packet_loss_pct: float | None


class WanUsageRead(ObservationRead):
    window_start: datetime
    device_id: str
    download_mbps: float
    upload_mbps: float
    active_devices: int


class WifiRadioObservationRead(ObservationRead):
    radio_id: str
    channel_utilization_pct: float


class SpeedProfileRead(BaseModel):
    subscribed_download_mbps: float | None
    subscribed_upload_mbps: float | None
    provisioned_download_mbps: float | None
    provisioned_upload_mbps: float | None


class DiagnosticServiceRead(BaseModel):
    id: str
    service_type: str
    subscription_status: str
    speed_profile: SpeedProfileRead | None
    latest_measurement: ServiceObservationRead | None


class DiagnosticDeviceRead(BaseModel):
    id: str
    device_type: str
    name: str
    inventory_status: str
    latest_measurement: DeviceObservationRead | None


class DiagnosticWifiNetworkRead(BaseModel):
    id: str
    router_device_id: str
    ssid: str
    band_ghz: float
    channel: int
    channel_width_mhz: int
    antenna_configuration: str
    wifi_standard: str


class DiagnosticWifiClientRead(BaseModel):
    client_device_id: str
    wifi_network_id: str
    latest_measurement: WifiObservationRead


class DiagnosticWarningRead(BaseModel):
    code: str
    resource_id: str | None = None
    message: str


class CustomerDiagnosticsRead(BaseModel):
    customer_ref: str
    customer_name: str
    installation_address: str
    is_demo: bool
    checked_at: datetime
    max_age_seconds: int
    services: list[DiagnosticServiceRead]
    devices: list[DiagnosticDeviceRead]
    wifi_networks: list[DiagnosticWifiNetworkRead]
    wifi_clients: list[DiagnosticWifiClientRead]
    wan_usage: list[WanUsageRead] = Field(default_factory=list)
    radio_measurements: list[WifiRadioObservationRead] = Field(default_factory=list)
    warnings: list[DiagnosticWarningRead] = Field(default_factory=list)
    requires_follow_up: bool = True
    scope_note: str = (
        "Stored observations only; no live test was run. Normal readings do not rule out "
        "an intermittent fault. No root cause or technician visit has been confirmed."
    )
