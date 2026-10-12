"""Isolated customer router simulation and action consent records."""

from alembic import op
import sqlalchemy as sa

revision = "0012_customer_agent_actions"
down_revision = "0011_customer_support"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("customer_router_states",
        sa.Column("device_id", sa.String(36), sa.ForeignKey("network_devices.id"), primary_key=True),
        sa.Column("reboot_count", sa.Integer(), nullable=False),
        sa.Column("service_vlans", sa.JSON(), nullable=False),
        sa.Column("last_action_at", sa.DateTime(timezone=True)))
    op.create_table("customer_router_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("customer_chat_conversations.id"), nullable=False),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("network_devices.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("service_type", sa.String(40)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "request_id", name="uq_customer_router_action_request"),
        sa.CheckConstraint("kind IN ('reboot', 'restore_vlan') AND status IN ('pending', 'succeeded', 'cancelled')", name="ck_customer_router_action"))
    op.create_index("ix_customer_router_actions_conversation_id", "customer_router_actions", ["conversation_id"])


def downgrade():
    op.drop_table("customer_router_actions")
    op.drop_table("customer_router_states")
