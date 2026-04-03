"""add user role and token version

Revision ID: 20260403_0002
Revises: 20260403_0001
Create Date: 2026-04-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260403_0002"
down_revision: str | None = "20260403_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_role = sa.Enum("admin", "user", name="userrole")
    user_role.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("role", user_role, nullable=True))
    op.add_column(
        "users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
    )

    op.execute("UPDATE users SET role = 'user' WHERE role IS NULL")

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("role", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("token_version")
        batch_op.drop_column("role")

    user_role = sa.Enum("admin", "user", name="userrole")
    user_role.drop(op.get_bind(), checkfirst=True)
