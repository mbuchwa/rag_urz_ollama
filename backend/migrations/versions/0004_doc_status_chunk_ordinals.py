"""Add document status tracking and chunk ordinals."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_doc_status_chunk_ordinals"
down_revision = "0003_add_oidc_sub_to_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="uploading",
        ),
    )
    op.add_column("documents", sa.Column("error", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute("UPDATE documents SET status = 'ingested'")
    op.alter_column("documents", "status", server_default=None)

    op.add_column(
        "chunks",
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("UPDATE chunks SET ordinal = 0")
    op.alter_column("chunks", "ordinal", server_default=None)


def downgrade() -> None:
    op.drop_column("chunks", "ordinal")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "error")
    op.drop_column("documents", "status")
