"""Separate Wi-Fi configuration and timestamped operational measurements."""

from alembic import op
import sqlalchemy as sa

revision = "0007_workforce_measurements"
down_revision = "0006_integrate_unifi_public"
branch_labels = None
depends_on = None


def _observation_columns():
    return [
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("quality", sa.String(30), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("topology_edges", sa.Column("link_type", sa.String(30), server_default="ethernet", nullable=False))
    op.create_table(
        "wifi_radios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("network_devices.id"), nullable=False),
        sa.Column("band_ghz", sa.Float(), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=False),
        sa.Column("channel_width_mhz", sa.Integer(), nullable=False),
        sa.Column("antenna_configuration", sa.String(30), nullable=False),
        sa.Column("wifi_standard", sa.String(40), nullable=False),
        sa.UniqueConstraint("device_id", "band_ghz", name="uq_wifi_radios_device_band"),
    )
    op.create_table(
        "wifi_networks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("radio_id", sa.String(36), sa.ForeignKey("wifi_radios.id"), nullable=False),
        sa.Column("ssid", sa.String(32), nullable=False),
        sa.Column("bssid", sa.String(17), unique=True, nullable=False),
    )
    op.create_table(
        "device_measurements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("network_devices.id"), nullable=False),
        *_observation_columns(),
        sa.Column("operational_status", sa.String(40), nullable=False),
        sa.Column("management_reachable", sa.Boolean()),
        sa.Column("wan_status", sa.String(40)),
        sa.Column("uptime_seconds", sa.Integer()),
        sa.Column("los_alarm", sa.Boolean()),
        sa.Column("optical_rx_dbm", sa.Float()),
        sa.Column("optical_tx_dbm", sa.Float()),
        sa.Column("test_connection", sa.String(20)),
        sa.Column("download_mbps", sa.Float()),
        sa.Column("upload_mbps", sa.Float()),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("packet_loss_pct", sa.Float()),
        sa.Column("disconnect_count_24h", sa.Integer()),
        sa.Column("disconnect_count_7d", sa.Integer()),
    )
    op.create_table(
        "wifi_client_measurements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_device_id", sa.String(36), sa.ForeignKey("network_devices.id"), nullable=False),
        sa.Column("wifi_network_id", sa.String(36), sa.ForeignKey("wifi_networks.id"), nullable=False),
        *_observation_columns(),
        sa.Column("connected", sa.Boolean(), nullable=False),
        sa.Column("rssi_dbm", sa.Float()),
        sa.Column("snr_db", sa.Float()),
        sa.Column("tx_link_mbps", sa.Float()),
        sa.Column("rx_link_mbps", sa.Float()),
        sa.Column("retry_pct", sa.Float()),
    )
    op.create_table(
        "service_measurements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_id", sa.String(36), sa.ForeignKey("services.id"), nullable=False),
        *_observation_columns(),
        sa.Column("operational_status", sa.String(40), nullable=False),
        sa.Column("registration_status", sa.String(40)),
        sa.Column("stream_status", sa.String(40)),
        sa.Column("multicast_joined", sa.Boolean()),
        sa.Column("vlan_id", sa.Integer()),
        sa.Column("jitter_ms", sa.Float()),
        sa.Column("packet_loss_pct", sa.Float()),
        sa.Column("last_error", sa.String(255)),
    )
    for table, target in (
        ("device_measurements", "device_id"),
        ("wifi_client_measurements", "client_device_id"),
        ("service_measurements", "service_id"),
    ):
        op.create_index(f"ix_{table}_{target}", table, [target])
        op.create_index(f"ix_{table}_observed_at", table, ["observed_at"])


def downgrade() -> None:
    op.drop_table("service_measurements")
    op.drop_table("wifi_client_measurements")
    op.drop_table("device_measurements")
    op.drop_table("wifi_networks")
    op.drop_table("wifi_radios")
    op.drop_column("topology_edges", "link_type")
