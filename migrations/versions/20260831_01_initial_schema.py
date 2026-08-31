"""Create the application schema.

Revision ID: 20260831_01
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260831_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("bearer_token", sa.String(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
            sa.Column("is_admin", sa.Boolean(), server_default="0", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_bearer_token", "users", ["bearer_token"], unique=True)
    else:
        user_indexes = {
            index["name"] for index in sa.inspect(bind).get_indexes("users")
        }
        if "ix_users_bearer_token" not in user_indexes:
            op.create_index(
                "ix_users_bearer_token", "users", ["bearer_token"], unique=True
            )
    op.execute(sa.text("UPDATE users SET bearer_token = NULL WHERE is_admin = 1"))

    if "cached_tiles" not in tables:
        op.create_table(
            "cached_tiles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tile_id", sa.String(), nullable=False),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column(
                "last_used_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tile_id"),
        )
        op.create_index("ix_cached_tiles_expires_at", "cached_tiles", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_cached_tiles_expires_at", table_name="cached_tiles")
    op.drop_table("cached_tiles")
    op.drop_index("ix_users_bearer_token", table_name="users")
    if "ix_users_email" in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("users")
    }:
        op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
