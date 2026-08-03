"""tool_call_logs table for MCP tool-call observability

Revision ID: 007_tool_call_logs
Revises: 006_chat_messages
Create Date: 2026-08-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007_tool_call_logs"
down_revision: Union[str, None] = "006_chat_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_call_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("database", sa.String(length=128), nullable=True),
        sa.Column("args_json", sa.JSON(), nullable=True),
        sa.Column("results_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tool_call_logs_session_created",
        "tool_call_logs",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_tool_call_logs_session_created", table_name="tool_call_logs")
    op.drop_table("tool_call_logs")
