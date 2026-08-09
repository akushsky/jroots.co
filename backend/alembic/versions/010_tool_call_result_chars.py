"""result_chars column on tool_call_logs (token-cost observability)

Revision ID: 010_tool_call_result_chars
Revises: 009_payments_provider_unique
Create Date: 2026-08-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010_tool_call_result_chars"
down_revision: Union[str, None] = "009_payments_provider_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tool_call_logs", sa.Column("result_chars", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tool_call_logs", "result_chars")
