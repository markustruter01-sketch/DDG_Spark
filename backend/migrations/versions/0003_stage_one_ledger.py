from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_stage_one_ledger"
down_revision = "0002_service_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_source_checksum",
        "source",
        ["checksum"],
        unique=True,
    )
    op.add_column("ledger", sa.Column("user_id", postgresql.UUID(as_uuid=True)))
    op.add_column("ledger", sa.Column("harness", sa.Text()))
    op.add_column("ledger", sa.Column("routing_reason", sa.Text()))
    op.add_column(
        "ledger",
        sa.Column("unsupported_statements", postgresql.JSONB(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ledger_user_id_auth_user",
        "ledger",
        "auth_user",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_ledger_user_id_auth_user", "ledger", type_="foreignkey")
    op.drop_column("ledger", "unsupported_statements")
    op.drop_column("ledger", "routing_reason")
    op.drop_column("ledger", "harness")
    op.drop_column("ledger", "user_id")
    op.drop_index("uq_source_checksum", table_name="source")
