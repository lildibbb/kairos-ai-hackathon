"""Persist the simulated trace and structured result of each tool execution."""

from alembic import op
import sqlalchemy as sa

revision = "0015_tool_execution_result"
down_revision = "0014_service_orders"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tool_executions", sa.Column("result", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("tool_executions", "result")
