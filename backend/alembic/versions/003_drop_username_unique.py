"""drop unique constraint on users.username

Revision ID: 003_drop_username_unique
Revises: 002_image_paths
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op

revision: str = "003_drop_username_unique"
down_revision: Union[str, None] = "002_image_paths"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("users_username_key", "users", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("users_username_key", "users", ["username"])
