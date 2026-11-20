"""Stage 3 platform tables: the file catalogue and versioned mappings.

Written out in full (not built from the live schema) so a fresh database
always goes through the same steps. The agent identity gets no access.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_ingest_mappings"
down_revision = "0003_stage_one_ledger"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
NOW = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ingest_file",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("archive", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("records", sa.Integer(), nullable=False),
        sa.Column("columns", JSONB, nullable=False),
        sa.Column("date_columns", JSONB, nullable=False),
        sa.Column("first_date", sa.Date(), nullable=True),
        sa.Column("last_date", sa.Date(), nullable=True),
        sa.Column("sample", JSONB, nullable=False),
        sa.Column("catalogued_at", NOW, nullable=False),
        sa.CheckConstraint(
            "format IN ('table', 'document', 'unknown')",
            name="ck_ingest_file_format_allowed",
        ),
    )
    op.create_index(
        "uq_ingest_file_archive_path_checksum",
        "ingest_file",
        ["archive", "path", "checksum"],
        unique=True,
    )
    op.create_table(
        "ingest_mapping",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "file_id",
            UUID,
            sa.ForeignKey("ingest_file.id", name="fk_ingest_mapping_file_id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=True),
        sa.Column("fields", JSONB, nullable=False),
        sa.Column("refs", JSONB, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasons", JSONB, nullable=False),
        sa.Column("proposed_by", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "decided_by",
            UUID,
            sa.ForeignKey("auth_user.id", name="fk_ingest_mapping_decided_by"),
            nullable=True,
        ),
        sa.Column("decided_at", NOW, nullable=True),
        sa.Column("created_at", NOW, nullable=False),
        sa.CheckConstraint(
            "proposed_by IN ('rules', 'model', 'person')",
            name="ck_ingest_mapping_proposed_by_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'superseded')",
            name="ck_ingest_mapping_status_allowed",
        ),
        sa.UniqueConstraint("file_id", "version", name="uq_ingest_mapping_version"),
    )
    # At most one approved mapping per file, enforced by the database.
    op.execute(
        "CREATE UNIQUE INDEX uq_ingest_mapping_one_approved "
        "ON ingest_mapping (file_id) WHERE status = 'approved'"
    )
    for table in ("ingest_file", "ingest_mapping"):
        op.execute(f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM PUBLIC, omni_agent")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE {table} TO omni_platform")


def downgrade() -> None:
    op.drop_table("ingest_mapping")
    op.drop_table("ingest_file")
