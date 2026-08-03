"""chat_messages.scan_ids + scans watermark/session link for chat scan uploads

Revision ID: 008_chat_scan_links
Revises: 007_tool_call_logs
Create Date: 2026-08-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_chat_scan_links"
down_revision: Union[str, None] = "007_tool_call_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("scan_ids", sa.JSON(), nullable=True))
    with op.batch_alter_table("scans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "watermarked",
                sa.Boolean(),
                server_default="false",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("session_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_scans_session_id",
            "chat_sessions",
            ["session_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("scans") as batch_op:
        batch_op.drop_constraint("fk_scans_session_id", type_="foreignkey")
        batch_op.drop_column("session_id")
        batch_op.drop_column("watermarked")
    op.drop_column("chat_messages", "scan_ids")
