"""Link a customer chatbot report to the staff ticket it mirrors."""

from alembic import op
import sqlalchemy as sa

revision = "0013_customer_report_ticket_link"
down_revision = "0012_customer_agent_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customer_trouble_tickets", sa.Column("ticket_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_customer_trouble_tickets_ticket_id", "customer_trouble_tickets", "tickets",
        ["ticket_id"], ["id"],
    )
    op.create_unique_constraint(
        "uq_customer_trouble_tickets_ticket_id", "customer_trouble_tickets", ["ticket_id"],
    )


def downgrade():
    op.drop_constraint("uq_customer_trouble_tickets_ticket_id", "customer_trouble_tickets", type_="unique")
    op.drop_constraint("fk_customer_trouble_tickets_ticket_id", "customer_trouble_tickets", type_="foreignkey")
    op.drop_column("customer_trouble_tickets", "ticket_id")
