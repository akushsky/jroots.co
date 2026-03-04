"""add image_file_path, thumbnail_file_path columns and users.email unique index

Revision ID: 002_image_paths
Revises: 001_baseline
Create Date: 2026-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_image_paths"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("images", sa.Column("image_file_path", sa.String(), nullable=True))
    op.add_column("images", sa.Column("thumbnail_file_path", sa.String(), nullable=True))

    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_constraint("uq_users_email", "users", type_="unique")

    op.drop_column("images", "thumbnail_file_path")
    op.drop_column("images", "image_file_path")
