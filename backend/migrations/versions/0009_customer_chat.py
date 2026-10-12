"""Separate, account-scoped customer conversation history."""

from alembic import op
import sqlalchemy as sa

revision = "0009_customer_chat"
down_revision = "0008_customer_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_chat_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_chat_conversations_user_id", "customer_chat_conversations", ["user_id"])
    op.create_table(
        "customer_chat_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("customer_chat_conversations.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("answer_choice", sa.String(40), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "request_id", name="uq_customer_chat_request"),
        sa.UniqueConstraint("conversation_id", "position", name="uq_customer_chat_position"),
    )
    op.create_index("ix_customer_chat_turns_conversation_id", "customer_chat_turns", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("customer_chat_turns")
    op.drop_table("customer_chat_conversations")
