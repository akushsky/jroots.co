"""unique constraint on credit_transactions (user_id, reason, ref_id)

Makes credit grants atomically idempotent: concurrent/retried grants with the
same ref_id hit INSERT ... ON CONFLICT DO NOTHING instead of double-crediting.
NULL ref_id rows never conflict (SQL-standard UNIQUE semantics on PG and sqlite).

Batch mode is used so the constraint can be added/dropped on SQLite as well
(copy-and-move strategy; a no-op passthrough on PostgreSQL).

Revision ID: 005_credit_tx_unique
Revises: 004_credits_billing
Create Date: 2026-08-03

"""

from typing import Sequence, Union

from alembic import op

revision: str = "005_credit_tx_unique"
down_revision: Union[str, None] = "004_credits_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("credit_transactions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_transactions_user_reason_ref",
            ["user_id", "reason", "ref_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("credit_transactions") as batch_op:
        batch_op.drop_constraint(
            "uq_credit_transactions_user_reason_ref",
            type_="unique",
        )
