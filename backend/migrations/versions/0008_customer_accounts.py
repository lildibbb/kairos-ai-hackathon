"""Link authenticated customer users to their household records."""

from alembic import op
import sqlalchemy as sa

revision = "0008_customer_accounts"
down_revision = "0007_workforce_measurements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_accounts",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
    )
    op.create_index("ix_customer_accounts_customer_id", "customer_accounts", ["customer_id"])


def downgrade() -> None:
    op.drop_table("customer_accounts")
