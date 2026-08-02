"""credits/billing foundation for LLM chat monetization

Revision ID: 004_credits_billing
Revises: 003_drop_username_unique
Create Date: 2026-08-03

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_credits_billing"
down_revision: Union[str, None] = "003_drop_username_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credits",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("searches_left", sa.Integer(), server_default="0", nullable=False),
        sa.Column("scans_left", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("delta_searches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("delta_scans", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("ref_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_credit_transactions_user_created",
        "credit_transactions",
        ["user_id", "created_at"],
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tariff", sa.String(length=32), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("raw_payload_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_payment_id"),
    )

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_free", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("tokens_used", sa.Integer(), server_default="0", nullable=True),
        sa.Column("tool_calls", sa.Integer(), server_default="0", nullable=True),
        sa.Column("model_main", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("charged", sa.Boolean(), server_default="false", nullable=True),
        sa.Column("query_summary", sa.Text(), nullable=True),
        sa.Column("results_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_sub_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "daily_budget",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "free_spend_usd", sa.Numeric(10, 4), server_default="0", nullable=False
        ),
        sa.PrimaryKeyConstraint("day"),
    )

    op.add_column(
        "users", sa.Column("fingerprint_hash", sa.String(length=128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "fingerprint_hash")

    op.drop_table("daily_budget")
    op.drop_table("subscriptions")
    op.drop_table("scans")
    op.drop_table("searches")
    op.drop_table("chat_sessions")
    op.drop_table("payments")
    op.drop_index(
        "ix_credit_transactions_user_created", table_name="credit_transactions"
    )
    op.drop_table("credit_transactions")
    op.drop_table("credits")
