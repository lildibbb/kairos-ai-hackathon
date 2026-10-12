"""Customer triage evidence, approved sales catalogue and visit scheduling."""

from alembic import op
import sqlalchemy as sa

revision = "0011_customer_support"
down_revision = "0010_customer_dispatch"
branch_labels = None
depends_on = None


def identifier():
    return sa.Column("id", sa.String(36), primary_key=True)


def timestamp(name):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def upgrade():
    op.create_table("wan_usage_samples", identifier(),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("network_devices.id"), nullable=False),
        timestamp("window_start"), timestamp("window_end"), timestamp("ingested_at"),
        sa.Column("download_mbps", sa.Float(), nullable=False), sa.Column("upload_mbps", sa.Float(), nullable=False),
        sa.Column("active_devices", sa.Integer(), nullable=False), sa.Column("source", sa.String(60), nullable=False),
        sa.Column("quality", sa.String(30), nullable=False),
        sa.CheckConstraint("window_end > window_start AND download_mbps >= 0 AND upload_mbps >= 0 AND active_devices >= 0", name="ck_wan_usage_values"))
    op.create_index("ix_wan_usage_samples_device_id", "wan_usage_samples", ["device_id"])
    op.create_table("wifi_radio_measurements", identifier(),
        sa.Column("radio_id", sa.String(36), sa.ForeignKey("wifi_radios.id"), nullable=False),
        timestamp("observed_at"), timestamp("ingested_at"),
        sa.Column("channel_utilization_pct", sa.Float(), nullable=False),
        sa.Column("source", sa.String(60), nullable=False), sa.Column("quality", sa.String(30), nullable=False),
        sa.CheckConstraint("channel_utilization_pct BETWEEN 0 AND 100", name="ck_radio_utilization"))
    op.create_index("ix_wifi_radio_measurements_radio_id", "wifi_radio_measurements", ["radio_id"])
    op.create_table("product_offers", identifier(),
        sa.Column("code", sa.String(80), unique=True, nullable=False),
        sa.Column("category", sa.String(20), nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(400), nullable=False), sa.Column("official_url", sa.String(400), nullable=False),
        sa.Column("monthly_price_myr", sa.Float()), sa.Column("contract_months", sa.Integer()), sa.Column("download_mbps", sa.Integer()),
        sa.Column("eligibility_note", sa.String(400), nullable=False), sa.Column("eligibility", sa.String(40), nullable=False),
        sa.Column("compatible_models", sa.JSON(), nullable=False),
        timestamp("valid_from"), timestamp("valid_until"), timestamp("verified_at"),
        sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.CheckConstraint("category IN ('mesh', 'plan') AND (monthly_price_myr IS NULL OR monthly_price_myr >= 0)", name="ck_product_offer_values"))
    op.create_table("store_locations", identifier(),
        sa.Column("code", sa.String(80), unique=True, nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("postcode", sa.String(5), nullable=False), sa.Column("address", sa.String(400), nullable=False),
        sa.Column("opening_hours", sa.String(200), nullable=False), sa.Column("official_url", sa.String(400), nullable=False),
        sa.Column("offers_sales", sa.Boolean(), nullable=False), timestamp("verified_at"),
        sa.Column("is_active", sa.Boolean(), nullable=False))
    op.create_index("ix_store_locations_postcode", "store_locations", ["postcode"])
    op.create_table("technician_shifts", identifier(),
        sa.Column("technician_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        timestamp("starts_at"), timestamp("ends_at"), sa.Column("kind", sa.String(20), nullable=False),
        sa.CheckConstraint("ends_at > starts_at AND kind IN ('working', 'unavailable')", name="ck_technician_shift"))
    op.create_index("ix_technician_shifts_technician_id", "technician_shifts", ["technician_id"])
    op.create_table("appointment_slots", identifier(),
        sa.Column("technician_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        timestamp("starts_at"), timestamp("ends_at"), timestamp("reserved_until"),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("ends_at > starts_at AND reserved_until >= ends_at", name="ck_appointment_slot_times"),
        sa.UniqueConstraint("technician_id", "starts_at", name="uq_technician_slot_start"))
    op.create_index("ix_appointment_slots_technician_id", "appointment_slots", ["technician_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute("ALTER TABLE appointment_slots ADD CONSTRAINT ex_technician_slot_overlap EXCLUDE USING gist (technician_id WITH =, tstzrange(starts_at, reserved_until, '[)') WITH &&) WHERE (is_active)")
    op.create_table("appointments", identifier(),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("customer_trouble_tickets.id"), nullable=False),
        sa.Column("slot_id", sa.String(36), sa.ForeignKey("appointment_slots.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_appointment_status"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_appointment_retry"))
    op.create_index("ix_appointments_ticket_id", "appointments", ["ticket_id"])
    for name, column in (("uq_active_appointment_slot", "slot_id"), ("uq_active_appointment_ticket", "ticket_id")):
        op.create_index(name, "appointments", [column], unique=True,
            postgresql_where=sa.text("status = 'confirmed'"), sqlite_where=sa.text("status = 'confirmed'"))


def downgrade():
    for table in ("appointments", "appointment_slots", "technician_shifts", "store_locations", "product_offers", "wifi_radio_measurements", "wan_usage_samples"):
        op.drop_table(table)
