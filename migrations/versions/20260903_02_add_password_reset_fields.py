"""Add password reset fields.

Revision ID: 20260903_02
Revises: 20260831_01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260903_02"
down_revision: str | None = "20260831_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("reset_token_hash", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "reset_token_expires_at", sa.DateTime(timezone=True), nullable=True
            )
        )
        batch_op.create_index("ix_users_reset_token_hash", ["reset_token_hash"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_reset_token_hash")
        batch_op.drop_column("reset_token_expires_at")
        batch_op.drop_column("reset_token_hash")
