"""Create core application tables."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision = "0002_create_core_tables"
down_revision = "0001_create_pgvector_extension"
branch_labels = None
depends_on = None


def _pg_trgm_available(conn: sa.engine.Connection) -> bool:
    result = conn.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm'"))
    return result.scalar() is not None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "namespaces",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(length=255), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "namespace_members",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("namespace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("namespace_id", "user_id", name="uq_namespace_members_user_namespace"),
    )
    op.create_index("ix_namespace_members_namespace_id", "namespace_members", ["namespace_id"])
    op.create_index("ix_namespace_members_user_id", "namespace_members", ["user_id"])

    op.create_table(
        "documents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("namespace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("uri", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=False, server_default="text/plain"),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("text_preview", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_onupdate=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_documents_namespace_id", "documents", ["namespace_id"])

    op.create_table(
        "jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("namespace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", pg.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            server_onupdate=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_jobs_namespace_id", "jobs", ["namespace_id"])

    op.create_table(
        "conversations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("namespace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_onupdate=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_conversations_namespace_id", "conversations", ["namespace_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_user_id", "messages", ["user_id"])

    op.create_table(
        "chunks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("namespace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("vector", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_namespace_id", "chunks", ["namespace_id"])
    op.create_index(
        "ix_chunks_vector_ivfflat",
        "chunks",
        ["vector"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )

    conn = op.get_bind()
    if _pg_trgm_available(conn):
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        op.create_index(
            "ix_chunks_text_trgm",
            "chunks",
            ["text"],
            postgresql_using="gin",
            postgresql_ops={"text": "gin_trgm_ops"},
        )


def _drop_index_if_exists(name: str, table_name: str) -> None:
    conn = op.get_bind()
    exists = conn.execute(sa.text("SELECT to_regclass(:name)"), {"name": name}).scalar()
    if exists:
        op.drop_index(name, table_name=table_name)


def downgrade() -> None:
    _drop_index_if_exists("ix_chunks_text_trgm", "chunks")
    op.drop_index("ix_chunks_vector_ivfflat", table_name="chunks")
    op.drop_index("ix_chunks_namespace_id", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")

    op.drop_index("ix_messages_user_id", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_conversations_namespace_id", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("ix_jobs_namespace_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_documents_namespace_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_namespace_members_user_id", table_name="namespace_members")
    op.drop_index("ix_namespace_members_namespace_id", table_name="namespace_members")
    op.drop_table("namespace_members")

    op.drop_table("namespaces")
    op.drop_table("users")
