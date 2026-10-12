from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from app.domain.appointment_schemas import AppointmentRead

CREDENTIAL_KEYS = (
    "onu_password",
    "ppp_password",
    "wifi_password",
    "vobb_password",
    "iptv_password",
    "password",
    "passphrase",
    "credential",
    "secret",
)
REDACTED_PLACEHOLDER = "[redacted]"


def redact_details(details: dict | None) -> dict:
    """Return a copy of a detail mapping with credential-shaped values masked."""
    if not details:
        return {}
    return {
        key: REDACTED_PLACEHOLDER if key.lower() in CREDENTIAL_KEYS else value
        for key, value in details.items()
    }


def find_credential(details: dict | None) -> tuple[str, str] | None:
    """Return the first credential-shaped key/value pair, or None when absent."""
    if not details:
        return None
    for key in CREDENTIAL_KEYS:
        value = details.get(key)
        if isinstance(value, str) and value:
            return key, value
    return None


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DemoEventRead(ORMModel):
    id: str
    source_event_id: str
    event_type: str
    processed_at: datetime | None


class PendingEventRead(ORMModel):
    id: str
    source_event_id: str
    event_type: str
    device_id: str
    device_ref: str
    device_name: str
    device_status: str
    service_id: str | None = None
    service_ref: str | None = None
    payload: dict
    received_at: datetime


class ProcessedTicketRead(ORMModel):
    id: str
    source_event_id: str
    customer_id: str
    service_id: str | None = None
    assigned_technician_id: str
    severity: str
    status: str
    summary: str


class ProcessEventResponse(ORMModel):
    ticket: ProcessedTicketRead
    created: bool
    duplicate: bool
    source_event_id: str
    assigned_technician_name: str


class TicketRead(ORMModel):
    id: str
    source_event_id: str
    customer_id: str
    service_id: str | None = None
    assigned_technician_id: str
    severity: str
    status: str
    summary: str
    tm_ticket_no: str | None = None
    ctt_activity_id: str | None = None
    login_id: str | None = None
    ticket_category: str | None = None
    ticket_created_at: datetime | None = None
    staff_code: str | None = None


class AssignedTicketRead(TicketRead):
    customer_ref: str
    customer_name: str
    service_type: str | None = None
    service_ref: str | None = None
    appointment: AppointmentRead | None = None
    customer_report_reference: str | None = None


class CustomerRead(ORMModel):
    id: str
    customer_ref: str
    name: str
    address: str
    is_demo: bool
    account_no: str | None = None
    contact_no: str | None = None
    email_address: str | None = None
    contract_term: int | None = None
    commitment_start: datetime | None = None
    commitment_end: datetime | None = None


class ServiceRead(ORMModel):
    id: str
    service_type: str
    service_ref: str
    status: str
    details: dict
    credential_available: bool = False

    @field_validator("details")
    @classmethod
    def _redact_credentials(cls, value: dict) -> dict:
        return redact_details(value)


class DeviceRead(ORMModel):
    id: str
    device_ref: str
    device_type: str
    name: str
    status: str
    credential_available: bool = False
    mac_address: str | None = None
    login_id: str | None = None
    friendly_name: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    cloud_device_type: str | None = None
    link_type: str | None = None
    ip_address: str | None = None
    ssid_2_4ghz: str | None = None
    ssid_5ghz: str | None = None
    channel_2_4ghz: int | None = None
    channel_5ghz: int | None = None
    antenna_2_4ghz: str | None = None
    antenna_5ghz: str | None = None
    protocol_2_4ghz: str | None = None
    protocol_5ghz: str | None = None
    rssi: int | None = None
    rx_rate: int | None = None
    tx_rate: int | None = None
    last_seen: datetime | None = None
    parent_mac: str | None = None
    platform: str | None = None
    bandwidth_2_4ghz: str | None = None
    bandwidth_5ghz: str | None = None

    @field_validator("ip_address", mode="before")
    @classmethod
    def _coerce_ip_address(cls, value: object) -> str | None:
        return None if value is None else str(value)


class RouterRead(ORMModel):
    serial_number: str
    login_id: str
    manufacturer: str | None = None
    model: str | None = None
    cpu_usage_pct: int | None = None
    cpu_temperature_c: int | None = None
    memory_usage_pct: int | None = None
    monthly_usage_gb: float | None = None
    rx_power_dbm: float | None = None


class CustomerSummaryRead(ORMModel):
    login_id: str
    summary: str
    recommendation: str | None = None
    model: str | None = None
    generated_at: datetime | None = None


class TicketDetailRead(ORMModel):
    ticket: TicketRead
    assigned_technician_name: str
    customer: CustomerRead
    services: list[ServiceRead]
    devices: list[DeviceRead]
    routers: list[RouterRead] = []
    customer_summary: CustomerSummaryRead | None = None
    appointment: AppointmentRead | None = None


class CustomerDetailRead(ORMModel):
    customer: CustomerRead
    services: list[ServiceRead]
    devices: list[DeviceRead]
    routers: list[RouterRead] = []
    customer_summary: CustomerSummaryRead | None = None


class NetworkCustomerRead(ORMModel):
    customer: CustomerRead
    devices: list[DeviceRead]
    routers: list[RouterRead]
    summary: CustomerSummaryRead | None = None


class TopologyNodeRead(ORMModel):
    device_id: str
    device_ref: str
    device_type: str
    name: str
    status: str
    service_id: str | None = None
    service_ref: str | None = None


class TopologyEdgeRead(ORMModel):
    source_device_id: str
    target_device_id: str
    service_id: str | None = None
    service_ref: str | None = None


class TopologyPathRead(ORMModel):
    ticket_id: str
    service_id: str | None = None
    service_ref: str | None = None
    nodes: list[TopologyNodeRead]
    edges: list[TopologyEdgeRead]


class CredentialRevealRead(ORMModel):
    device_id: str
    device_ref: str
    credential_type: str
    credential: str


class ServiceCredentialRevealRead(ORMModel):
    service_id: str
    service_ref: str
    credential_type: str
    credential: str


class EntityFactRead(BaseModel):
    entity_type: str
    entity_id: str
    group_key: str
    field_key: str
    label: str
    value_text: str | None = None
    value_number: float | None = None
    is_sensitive: bool = False

    @model_validator(mode="after")
    def _redact_sensitive(self):
        if self.is_sensitive and self.value_text is not None:
            self.value_text = REDACTED_PLACEHOLDER
        return self


class TicketFactsRead(BaseModel):
    ticket_id: str
    facts: list[EntityFactRead]
