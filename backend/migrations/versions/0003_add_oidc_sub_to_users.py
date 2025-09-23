"""Add OIDC subject column to users."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_oidc_sub_to_users"
down_revision = "0002_create_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oidc_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_users_oidc_sub", "users", ["oidc_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_oidc_sub", table_name="users")
    op.drop_column("users", "oidc_sub")
