"""Allowlisted agent tools.

The assistant may *propose* a tool, but nothing here executes anything on its
own. Each tool declares the roles that may use it, a risk tier, the target
device types it accepts, whether explicit confirmation is required, and a
Pydantic parameter model so model-supplied arguments are treated as untrusted
input.
"""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ToolKind = Literal["read_only", "stateful"]
ToolRisk = Literal["low", "medium", "high"]
ToolCategory = Literal["diagnostics", "wifi", "optical", "service", "network"]

# Only these configuration keys may be changed, with inclusive integer bounds.
CONFIG_BOUNDS: dict[str, tuple[int, int]] = {
    "wifi_channel": (1, 13),
    "tx_power_dbm": (0, 30),
}

# Per-band channel bounds for the router radio. The 2.4 GHz band uses the
# 1-13 range exposed by update_config; the 5 GHz band uses the UNII-1/3 span.
BAND_CHANNEL_BOUNDS: dict[str, tuple[int, int]] = {
    "2.4": (1, 13),
    "5": (36, 165),
}

TECHNICIAN_ROLES = ("technician",)
ANY_WORK_ROLES = ("technician", "operator", "supervisor")

_SSID_PATTERN = re.compile(r"^[ -~]{1,32}$")
_MAC_PATTERN = re.compile(r"^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$")


class _StrictParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceTargetParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)


class UpdateConfigParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)
    settings: dict[str, int]

    @field_validator("settings")
    @classmethod
    def _validate_settings(cls, value: dict[str, int]) -> dict[str, int]:
        if not value:
            raise ValueError("At least one configuration setting is required")
        for key, setting in value.items():
            if key not in CONFIG_BOUNDS:
                raise ValueError(f"Unsupported configuration key: {key}")
            if isinstance(setting, bool) or not isinstance(setting, int):
                raise ValueError(f"{key} must be an integer")
            low, high = CONFIG_BOUNDS[key]
            if not low <= setting <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
        return value


class SetSsidParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)
    ssid_2g: str | None = None
    ssid_5g: str | None = None

    @field_validator("ssid_2g", "ssid_5g")
    @classmethod
    def _validate_ssid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _SSID_PATTERN.match(value):
            raise ValueError("SSID must be 1-32 printable ASCII characters")
        return value

    @model_validator(mode="after")
    def _require_one_band(self) -> "SetSsidParams":
        if self.ssid_2g is None and self.ssid_5g is None:
            raise ValueError("Provide at least one of ssid_2g or ssid_5g")
        return self


class SetChannelParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)
    band: Literal["2.4", "5"]
    channel: int

    @field_validator("channel")
    @classmethod
    def _validate_channel(cls, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("channel must be an integer")
        return value

    @model_validator(mode="after")
    def _channel_within_band(self) -> "SetChannelParams":
        low, high = BAND_CHANNEL_BOUNDS[self.band]
        if not low <= self.channel <= high:
            raise ValueError(f"channel for {self.band} GHz must be between {low} and {high}")
        return self


class RestartServiceParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)
    service: Literal["hsi", "vobb", "iptv"]


class BlockClientParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)
    client_mac: str

    @field_validator("client_mac")
    @classmethod
    def _validate_mac(cls, value: str) -> str:
        if not _MAC_PATTERN.match(value):
            raise ValueError("client_mac must be a colon-separated MAC address")
        return value.lower()


class DhcpReservationParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)
    client_mac: str
    ip_address: str

    @field_validator("client_mac")
    @classmethod
    def _validate_mac(cls, value: str) -> str:
        if not _MAC_PATTERN.match(value):
            raise ValueError("client_mac must be a colon-separated MAC address")
        return value.lower()

    @field_validator("ip_address")
    @classmethod
    def _validate_ip(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 4 or any(not part.isdigit() or not 0 <= int(part) <= 255 for part in parts):
            raise ValueError("ip_address must be a valid IPv4 address")
        return value


class ClientBandParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)
    client_mac: str
    target_band: Literal["2.4", "5"] = "5"

    @field_validator("client_mac")
    @classmethod
    def _validate_mac(cls, value: str) -> str:
        if not _MAC_PATTERN.match(value):
            raise ValueError("client_mac must be a colon-separated MAC address")
        return value.lower()


class QosPriorityParams(_StrictParams):
    device_id: str = Field(min_length=1, max_length=64)
    client_mac: str
    priority: Literal["high", "normal", "low"] = "high"

    @field_validator("client_mac")
    @classmethod
    def _validate_mac(cls, value: str) -> str:
        if not _MAC_PATTERN.match(value):
            raise ValueError("client_mac must be a colon-separated MAC address")
        return value.lower()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    kind: ToolKind
    category: ToolCategory
    risk: ToolRisk
    allowed_roles: tuple[str, ...]
    requires_confirmation: bool
    target_device_types: tuple[str, ...] | None
    params: type[BaseModel]


TOOL_SPECS: dict[str, ToolSpec] = {
    "get_device_status": ToolSpec(
        name="get_device_status",
        title="Read device status",
        description="Read the current simulated status of a customer device.",
        kind="read_only",
        category="diagnostics",
        risk="low",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=False,
        target_device_types=None,
        params=DeviceTargetParams,
    ),
    "list_connected_clients": ToolSpec(
        name="list_connected_clients",
        title="List connected clients",
        description="List the simulated Wi-Fi/Ethernet clients on a home router.",
        kind="read_only",
        category="diagnostics",
        risk="low",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=False,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
    "run_speed_test": ToolSpec(
        name="run_speed_test",
        title="Run throughput test",
        description="Run a simulated HSI throughput test against the router WAN path.",
        kind="read_only",
        category="diagnostics",
        risk="low",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=False,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
    "run_optical_diagnostics": ToolSpec(
        name="run_optical_diagnostics",
        title="Run optical diagnostics",
        description="Read simulated receive power and LOS state from an ONU or OLT port.",
        kind="read_only",
        category="diagnostics",
        risk="low",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=False,
        target_device_types=("ONU", "OLT"),
        params=DeviceTargetParams,
    ),
    "reboot_router": ToolSpec(
        name="reboot_router",
        title="Reboot home router",
        description="Simulate a reboot of the customer's home router.",
        kind="stateful",
        category="diagnostics",
        risk="medium",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
    "reboot_ont": ToolSpec(
        name="reboot_ont",
        title="Reboot ONU",
        description="Simulate a power-cycle of the customer's optical network unit.",
        kind="stateful",
        category="optical",
        risk="medium",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("ONU",),
        params=DeviceTargetParams,
    ),
    "refresh_ont_registration": ToolSpec(
        name="refresh_ont_registration",
        title="Refresh ONU registration",
        description="Re-register the ONU with the OLT to restore the PON link.",
        kind="stateful",
        category="optical",
        risk="medium",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("ONU",),
        params=DeviceTargetParams,
    ),
    "reset_optical_port": ToolSpec(
        name="reset_optical_port",
        title="Reset optical port",
        description="Reset the OLT/ONU optical port and re-baseline receive power.",
        kind="stateful",
        category="optical",
        risk="high",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("ONU", "OLT"),
        params=DeviceTargetParams,
    ),
    "update_config": ToolSpec(
        name="update_config",
        title="Update radio configuration",
        description="Simulate a bounded configuration change on the home router.",
        kind="stateful",
        category="wifi",
        risk="medium",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=UpdateConfigParams,
    ),
    "set_wifi_ssid": ToolSpec(
        name="set_wifi_ssid",
        title="Change Wi-Fi SSID",
        description="Rename the simulated 2.4 GHz and/or 5 GHz Wi-Fi network.",
        kind="stateful",
        category="wifi",
        risk="medium",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=SetSsidParams,
    ),
    "set_wifi_channel": ToolSpec(
        name="set_wifi_channel",
        title="Change Wi-Fi channel",
        description="Move a router radio to a specific channel on the named band.",
        kind="stateful",
        category="wifi",
        risk="medium",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=SetChannelParams,
    ),
    "flush_dns_cache": ToolSpec(
        name="flush_dns_cache",
        title="Flush DNS cache",
        description="Clear the router resolver cache to recover from stale DNS answers.",
        kind="stateful",
        category="network",
        risk="low",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
    "restart_service": ToolSpec(
        name="restart_service",
        title="Restart customer service",
        description="Simulate a restart of the customer's HSI, VoBB, or IPTV service on the router.",
        kind="stateful",
        category="service",
        risk="medium",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=RestartServiceParams,
    ),
    "block_client": ToolSpec(
        name="block_client",
        title="Quarantine a client",
        description="Block a misbehaving client MAC from the simulated router network.",
        kind="stateful",
        category="network",
        risk="high",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=BlockClientParams,
    ),
    "set_dhcp_reservation": ToolSpec(
        name="set_dhcp_reservation",
        title="Add DHCP reservation",
        description="Pin a client MAC to a fixed IP address on the simulated router.",
        kind="stateful",
        category="network",
        risk="high",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=DhcpReservationParams,
    ),
    "wifi_spectrum_scan": ToolSpec(
        name="wifi_spectrum_scan",
        title="Scan Wi-Fi spectrum",
        description="Sweep both radios for neighbouring networks and rank the least congested channels.",
        kind="read_only",
        category="wifi",
        risk="low",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=False,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
    "trace_service_path": ToolSpec(
        name="trace_service_path",
        title="Trace service path",
        description="Probe latency and loss hop by hop from the weakest client through the router, fibre and core to the internet.",
        kind="read_only",
        category="diagnostics",
        risk="low",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=False,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
    "client_signal_survey": ToolSpec(
        name="client_signal_survey",
        title="Survey client signal",
        description="Grade every wireless client's signal and link rate and flag coverage gaps.",
        kind="read_only",
        category="wifi",
        risk="low",
        allowed_roles=ANY_WORK_ROLES,
        requires_confirmation=False,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
    "steer_client_band": ToolSpec(
        name="steer_client_band",
        title="Steer client band",
        description="Ask a client to roam to the other radio band (802.11v BSS transition).",
        kind="stateful",
        category="wifi",
        risk="low",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=ClientBandParams,
    ),
    "set_qos_priority": ToolSpec(
        name="set_qos_priority",
        title="Prioritise client traffic",
        description="Give one client high, normal, or low traffic priority on the router (WMM/DSCP).",
        kind="stateful",
        category="network",
        risk="low",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=QosPriorityParams,
    ),
    "optimize_wifi_radio": ToolSpec(
        name="optimize_wifi_radio",
        title="Auto-optimise Wi-Fi",
        description="Scan, then move both radios to their cleanest channels and tune transmit power for coverage.",
        kind="stateful",
        category="wifi",
        risk="medium",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
    "upgrade_firmware": ToolSpec(
        name="upgrade_firmware",
        title="Upgrade router firmware",
        description="Install the latest signed firmware to the standby partition and reboot into it, keeping a rollback image.",
        kind="stateful",
        category="diagnostics",
        risk="high",
        allowed_roles=TECHNICIAN_ROLES,
        requires_confirmation=True,
        target_device_types=("router",),
        params=DeviceTargetParams,
    ),
}


def get_tool_spec(name: str) -> ToolSpec | None:
    return TOOL_SPECS.get(name)


def catalog_for_role(role: str) -> list[ToolSpec]:
    return [spec for spec in TOOL_SPECS.values() if role in spec.allowed_roles]
