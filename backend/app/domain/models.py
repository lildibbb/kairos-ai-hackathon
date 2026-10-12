import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ExcludeConstraint, INET
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import Settings
from app.db.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    staff_code: Mapped[str | None] = mapped_column(String(20), unique=True)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_ref: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    account_no: Mapped[str | None] = mapped_column(Text)
    contact_no: Mapped[str | None] = mapped_column(Text)
    email_address: Mapped[str | None] = mapped_column(Text)
    contract_term: Mapped[int | None] = mapped_column(Integer)
    commitment_start: Mapped[datetime | None] = mapped_column(DateTime)
    commitment_end: Mapped[datetime | None] = mapped_column(DateTime)


class CustomerAccount(Base):
    __tablename__ = "customer_accounts"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("customer_id", "service_type", name="uq_services_customer_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    service_type: Mapped[str] = mapped_column(String(40), nullable=False)
    service_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"), nullable=False)


class NetworkDevice(Base):
    __tablename__ = "network_devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"))
    device_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    device_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="unknown", server_default=text("'unknown'"), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"), nullable=False)
    mac_address: Mapped[str | None] = mapped_column(Text)
    login_id: Mapped[str | None] = mapped_column(Text)
    friendly_name: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    cloud_device_type: Mapped[str | None] = mapped_column(Text)
    link_type: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET().with_variant(String(45), "sqlite"))
    ssid_2_4ghz: Mapped[str | None] = mapped_column(Text)
    ssid_5ghz: Mapped[str | None] = mapped_column(Text)
    channel_2_4ghz: Mapped[int | None] = mapped_column(Integer)
    channel_5ghz: Mapped[int | None] = mapped_column(Integer)
    antenna_2_4ghz: Mapped[str | None] = mapped_column(Text)
    antenna_5ghz: Mapped[str | None] = mapped_column(Text)
    protocol_2_4ghz: Mapped[str | None] = mapped_column(Text)
    protocol_5ghz: Mapped[str | None] = mapped_column(Text)
    rssi: Mapped[int | None] = mapped_column(Integer)
    rx_rate: Mapped[int | None] = mapped_column(Integer)
    tx_rate: Mapped[int | None] = mapped_column(Integer)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    parent_mac: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(Text)
    bandwidth_2_4ghz: Mapped[str | None] = mapped_column(Text)
    bandwidth_5ghz: Mapped[str | None] = mapped_column(Text)


class Router(Base):
    __tablename__ = "routers"
    serial_number: Mapped[str] = mapped_column(Text, primary_key=True)
    login_id: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    cpu_usage_pct: Mapped[int | None] = mapped_column(Integer)
    cpu_temperature_c: Mapped[int | None] = mapped_column(Integer)
    memory_usage_pct: Mapped[int | None] = mapped_column(Integer)
    monthly_usage_gb: Mapped[float | None] = mapped_column(Numeric(9, 1))
    rx_power_dbm: Mapped[float | None] = mapped_column(Numeric(5, 1))


class CustomerSummary(Base):
    __tablename__ = "customer_summaries"
    login_id: Mapped[str] = mapped_column(Text, primary_key=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class TopologyEdge(Base):
    __tablename__ = "topology_edges"
    __table_args__ = (UniqueConstraint("source_device_id", "target_device_id", name="uq_topology_edge_path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), nullable=False)
    target_device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), nullable=False)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"))
    link_type: Mapped[str] = mapped_column(String(30), default="ethernet", server_default=text("'ethernet'"), nullable=False)


class WifiRadio(Base):
    __tablename__ = "wifi_radios"
    __table_args__ = (UniqueConstraint("device_id", "band_ghz", name="uq_wifi_radios_device_band"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), nullable=False)
    band_ghz: Mapped[float] = mapped_column(Float, nullable=False)
    channel: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_width_mhz: Mapped[int] = mapped_column(Integer, nullable=False)
    antenna_configuration: Mapped[str] = mapped_column(String(30), nullable=False)
    wifi_standard: Mapped[str] = mapped_column(String(40), nullable=False)


class WifiNetwork(Base):
    __tablename__ = "wifi_networks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    radio_id: Mapped[str] = mapped_column(ForeignKey("wifi_radios.id"), nullable=False)
    ssid: Mapped[str] = mapped_column(String(32), nullable=False)
    bssid: Mapped[str] = mapped_column(String(17), unique=True, nullable=False)


class DeviceMeasurement(Base):
    __tablename__ = "device_measurements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    quality: Mapped[str] = mapped_column(String(30), nullable=False)
    operational_status: Mapped[str] = mapped_column(String(40), nullable=False)
    management_reachable: Mapped[bool | None] = mapped_column(Boolean)
    wan_status: Mapped[str | None] = mapped_column(String(40))
    uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    los_alarm: Mapped[bool | None] = mapped_column(Boolean)
    optical_rx_dbm: Mapped[float | None] = mapped_column(Float)
    optical_tx_dbm: Mapped[float | None] = mapped_column(Float)
    test_connection: Mapped[str | None] = mapped_column(String(20))
    download_mbps: Mapped[float | None] = mapped_column(Float)
    upload_mbps: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    packet_loss_pct: Mapped[float | None] = mapped_column(Float)
    disconnect_count_24h: Mapped[int | None] = mapped_column(Integer)
    disconnect_count_7d: Mapped[int | None] = mapped_column(Integer)


class WifiClientMeasurement(Base):
    __tablename__ = "wifi_client_measurements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), nullable=False, index=True)
    wifi_network_id: Mapped[str] = mapped_column(ForeignKey("wifi_networks.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    quality: Mapped[str] = mapped_column(String(30), nullable=False)
    connected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rssi_dbm: Mapped[float | None] = mapped_column(Float)
    snr_db: Mapped[float | None] = mapped_column(Float)
    tx_link_mbps: Mapped[float | None] = mapped_column(Float)
    rx_link_mbps: Mapped[float | None] = mapped_column(Float)
    retry_pct: Mapped[float | None] = mapped_column(Float)


class ServiceMeasurement(Base):
    __tablename__ = "service_measurements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    quality: Mapped[str] = mapped_column(String(30), nullable=False)
    operational_status: Mapped[str] = mapped_column(String(40), nullable=False)
    registration_status: Mapped[str | None] = mapped_column(String(40))
    stream_status: Mapped[str | None] = mapped_column(String(40))
    multicast_joined: Mapped[bool | None] = mapped_column(Boolean)
    vlan_id: Mapped[int | None] = mapped_column(Integer)
    jitter_ms: Mapped[float | None] = mapped_column(Float)
    packet_loss_pct: Mapped[float | None] = mapped_column(Float)
    last_error: Mapped[str | None] = mapped_column(String(255))


class NetworkEvent(Base):
    __tablename__ = "network_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_event_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), nullable=False)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"))
    payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_event_id: Mapped[str] = mapped_column(ForeignKey("network_events.id"), unique=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"))
    assigned_technician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="open", server_default=text("'open'"), nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    # TMFORCE field-operations metadata. Nullable so non-TMFORCE tickets remain valid.
    tm_ticket_no: Mapped[str | None] = mapped_column(String(60), unique=True)
    ctt_activity_id: Mapped[str | None] = mapped_column(String(60))
    login_id: Mapped[str | None] = mapped_column(String(60))
    ticket_category: Mapped[str | None] = mapped_column(String(60))
    ticket_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staff_code: Mapped[str | None] = mapped_column(String(20))


class EntityFactSheet(Base):
    """Retrievable per-entity fact group, mirroring the knowledge chunk index.

    One row per ``(entity_type, entity_id, group_key)``. ``content`` is the
    rendered, secret-free field block that is embedded for retrieval; sensitive
    fields live only in ``EntityFact`` and never enter ``content``.
    """

    __tablename__ = "entity_fact_sheets"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "group_key", name="uq_fact_sheet_entity_group"),)
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    group_key: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(Settings().embedding_dimensions))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EntityFact(Base):
    """Typed field value for an entity, used for exact display and lookup."""

    __tablename__ = "entity_facts"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "field_key", name="uq_fact_entity_field"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    group_key: Mapped[str] = mapped_column(String(40), nullable=False)
    field_key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[float | None] = mapped_column(Float)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("document_key", "version", name="uq_document_version"),)
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    document_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "section", name="uq_chunk_document_section"),)
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), nullable=False)
    section: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(Settings().embedding_dimensions))


class CustomerChatConversation(Base):
    __tablename__ = "customer_chat_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CustomerChatTurn(Base):
    __tablename__ = "customer_chat_turns"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_customer_chat_request"),
        UniqueConstraint("conversation_id", "position", name="uq_customer_chat_position"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("customer_chat_conversations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    answer_choice: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CustomerRouterState(Base):
    """Showcase-only state; never replaces network inventory or live telemetry."""
    __tablename__ = "customer_router_states"
    device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), primary_key=True)
    reboot_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    service_vlans: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerRouterAction(Base):
    __tablename__ = "customer_router_actions"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_customer_router_action_request"),
        CheckConstraint("kind IN ('reboot', 'restore_vlan') AND status IN ('pending', 'succeeded', 'cancelled')", name="ck_customer_router_action"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("customer_chat_conversations.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    service_type: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DispatchArea(Base):
    __tablename__ = "dispatch_areas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CustomerDispatchArea(Base):
    __tablename__ = "customer_dispatch_areas"
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("dispatch_areas.id"), nullable=False)


class TechnicianDispatchArea(Base):
    __tablename__ = "technician_dispatch_areas"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("dispatch_areas.id"), primary_key=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CustomerTroubleTicket(Base):
    __tablename__ = "customer_trouble_tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("customer_chat_conversations.id"), unique=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    area_id: Mapped[str | None] = mapped_column(ForeignKey("dispatch_areas.id"))
    assigned_technician_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Field-operations ticket mirrored into the staff ``tickets`` table when a
    # chatbot report is auto-assigned. Null while the report is queued.
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"), unique=True)


class WanUsageSample(Base):
    __tablename__ = "wan_usage_samples"
    __table_args__ = (CheckConstraint("window_end > window_start AND download_mbps >= 0 AND upload_mbps >= 0 AND active_devices >= 0", name="ck_wan_usage_values"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("network_devices.id"), nullable=False, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    download_mbps: Mapped[float] = mapped_column(Float, nullable=False)
    upload_mbps: Mapped[float] = mapped_column(Float, nullable=False)
    active_devices: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    quality: Mapped[str] = mapped_column(String(30), nullable=False)

    @property
    def observed_at(self):
        return self.window_end


class WifiRadioMeasurement(Base):
    __tablename__ = "wifi_radio_measurements"
    __table_args__ = (CheckConstraint("channel_utilization_pct BETWEEN 0 AND 100", name="ck_radio_utilization"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    radio_id: Mapped[str] = mapped_column(ForeignKey("wifi_radios.id"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    channel_utilization_pct: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    quality: Mapped[str] = mapped_column(String(30), nullable=False)


class ProductOffer(Base):
    __tablename__ = "product_offers"
    __table_args__ = (CheckConstraint("category IN ('mesh', 'plan') AND (monthly_price_myr IS NULL OR monthly_price_myr >= 0)", name="ck_product_offer_values"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(400), nullable=False)
    official_url: Mapped[str] = mapped_column(String(400), nullable=False)
    monthly_price_myr: Mapped[float | None] = mapped_column(Float)
    contract_months: Mapped[int | None] = mapped_column(Integer)
    download_mbps: Mapped[int | None] = mapped_column(Integer)
    eligibility_note: Mapped[str] = mapped_column(String(400), nullable=False)
    eligibility: Mapped[str] = mapped_column(String(40), default="check_at_checkout", nullable=False)
    compatible_models: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StoreLocation(Base):
    __tablename__ = "store_locations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    postcode: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(400), nullable=False)
    opening_hours: Mapped[str] = mapped_column(String(200), nullable=False)
    official_url: Mapped[str] = mapped_column(String(400), nullable=False)
    offers_sales: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TechnicianShift(Base):
    __tablename__ = "technician_shifts"
    __table_args__ = (CheckConstraint("ends_at > starts_at AND kind IN ('working', 'unavailable')", name="ck_technician_shift"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    technician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="working", nullable=False)


class AppointmentSlot(Base):
    __tablename__ = "appointment_slots"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at AND reserved_until >= ends_at", name="ck_appointment_slot_times"),
        UniqueConstraint("technician_id", "starts_at", name="uq_technician_slot_start"),
        ExcludeConstraint(("technician_id", "="), (func.tstzrange(text("starts_at"), text("reserved_until"), "[)"), "&&"),
            where=text("is_active"), name="ex_technician_slot_overlap").ddl_if(dialect="postgresql"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    technician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CustomerAppointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_appointment_status"),
        UniqueConstraint("user_id", "request_id", name="uq_appointment_retry"),
        Index("uq_active_appointment_slot", "slot_id", unique=True, postgresql_where=text("status = 'confirmed'"), sqlite_where=text("status = 'confirmed'")),
        Index("uq_active_appointment_ticket", "ticket_id", unique=True, postgresql_where=text("status = 'confirmed'"), sqlite_where=text("status = 'confirmed'")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("customer_trouble_tickets.id"), nullable=False, index=True)
    slot_id: Mapped[str] = mapped_column(ForeignKey("appointment_slots.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("assistant_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str | None] = mapped_column(String(400))
    correlation_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
