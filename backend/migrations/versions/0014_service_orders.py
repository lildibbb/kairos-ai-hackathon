"""Store summarize.py order actions and the orders submitted from a ticket."""

from alembic import op
import sqlalchemy as sa

revision = "0014_service_orders"
down_revision = "0013_customer_report_ticket_link"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE customer_summaries ADD COLUMN IF NOT EXISTS actions TEXT")
    op.create_table(
        "service_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("product_code", sa.String(80), nullable=False),
        sa.Column("product_name", sa.String(160), nullable=False),
        sa.Column("monthly_price_myr", sa.Float(), nullable=True),
        sa.Column("one_time_price_myr", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("email_status", sa.String(20), nullable=False),
        sa.Column("email_recipient", sa.String(255), nullable=True),
        sa.Column("email_error", sa.String(400), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_service_orders_ticket_id", "service_orders", ["ticket_id"])


def downgrade():
    op.drop_index("ix_service_orders_ticket_id", table_name="service_orders")
    op.drop_table("service_orders")
    op.drop_column("customer_summaries", "actions")
