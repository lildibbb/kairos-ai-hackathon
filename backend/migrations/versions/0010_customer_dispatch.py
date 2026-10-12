"""Customer reports and explicit dispatch mappings, separate from event tickets."""

from alembic import op
import sqlalchemy as sa

revision = "0010_customer_dispatch"
down_revision = "0009_customer_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("dispatch_areas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(60), unique=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False))
    op.create_table("customer_dispatch_areas",
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), primary_key=True),
        sa.Column("area_id", sa.String(36), sa.ForeignKey("dispatch_areas.id"), nullable=False))
    op.create_table("technician_dispatch_areas",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("area_id", sa.String(36), sa.ForeignKey("dispatch_areas.id"), primary_key=True),
        sa.Column("is_available", sa.Boolean(), nullable=False))
    op.create_table("customer_trouble_tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("reference", sa.String(40), unique=True, nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("customer_chat_conversations.id"), unique=True, nullable=False),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("intent", sa.String(40), nullable=False),
        sa.Column("summary", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("area_id", sa.String(36), sa.ForeignKey("dispatch_areas.id")),
        sa.Column("assigned_technician_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_customer_trouble_tickets_customer_id", "customer_trouble_tickets", ["customer_id"])


def downgrade() -> None:
    op.drop_table("customer_trouble_tickets")
    op.drop_table("technician_dispatch_areas")
    op.drop_table("customer_dispatch_areas")
    op.drop_table("dispatch_areas")
