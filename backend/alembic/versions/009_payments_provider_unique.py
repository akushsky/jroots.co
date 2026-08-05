"""payments: UNIQUE(provider_payment_id) -> UNIQUE(provider, provider_payment_id)

Provider payment ids are only guaranteed unique within a provider's own
namespace; the dedupe logic keys on the (provider, provider_payment_id) pair,
so the constraint must match it.

On PostgreSQL the old constraint (created unnamed in 004, auto-named
payments_provider_payment_id_key) is dropped and recreated as a composite.
On SQLite a column-level UNIQUE becomes an internal autoindex that cannot be
dropped at all, so the table is rebuilt copy-and-move with explicit DDL.

Revision ID: 009_payments_provider_unique
Revises: 008_chat_scan_links
Create Date: 2026-08-05

"""

from typing import Sequence, Union

from alembic import op

revision: str = "009_payments_provider_unique"
down_revision: Union[str, None] = "008_chat_scan_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_CONSTRAINT = "uq_payments_provider_payment_id"

_COLUMNS = (
    "id, provider, provider_payment_id, order_id, user_id, tariff, "
    "amount, currency, status, raw_payload_json, created_at"
)


def _rebuild_sqlite(unique_clause: str) -> None:
    op.execute(f"""
        CREATE TABLE payments_new (
            id INTEGER NOT NULL,
            provider VARCHAR(32) NOT NULL,
            provider_payment_id VARCHAR(128) NOT NULL,
            order_id VARCHAR(128),
            user_id INTEGER NOT NULL,
            tariff VARCHAR(32),
            amount NUMERIC(10, 2),
            currency VARCHAR(8),
            status VARCHAR(32),
            raw_payload_json JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
            {unique_clause}
        )
        """)
    op.execute(f"INSERT INTO payments_new ({_COLUMNS}) SELECT {_COLUMNS} FROM payments")
    op.execute("DROP TABLE payments")
    op.execute("ALTER TABLE payments_new RENAME TO payments")


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _rebuild_sqlite(
            f"CONSTRAINT {NEW_CONSTRAINT} UNIQUE (provider, provider_payment_id)"
        )
        return
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint("payments_provider_payment_id_key", type_="unique")
        batch_op.create_unique_constraint(
            NEW_CONSTRAINT, ["provider", "provider_payment_id"]
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _rebuild_sqlite("UNIQUE (provider_payment_id)")
        return
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint(NEW_CONSTRAINT, type_="unique")
        batch_op.create_unique_constraint(None, ["provider_payment_id"])
