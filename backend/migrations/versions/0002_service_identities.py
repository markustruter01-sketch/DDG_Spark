from __future__ import annotations

import os
import re

from alembic import op

from omni.db.credentials import derive_role_password
from omni.model.schema import build_metadata, load_schema

revision = "0002_service_identities"
down_revision = "0001_foundations"
branch_labels = None
depends_on = None


def _create_or_reset_login(role_name: str) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for service role migration.")
    password = derive_role_password(database_url, role_name)
    # The role names are fixed constants and the derived password is hex encoded.
    op.execute(
        f"""
        DO $omni_role$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role_name}') THEN
            EXECUTE 'ALTER ROLE {role_name} LOGIN PASSWORD ''{password}''
              NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS';
          ELSE
            EXECUTE 'CREATE ROLE {role_name} LOGIN PASSWORD ''{password}''
              NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS';
          END IF;
        END
        $omni_role$;
        """
    )


def upgrade() -> None:
    _create_or_reset_login("omni_platform")
    _create_or_reset_login("omni_agent")

    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO omni_platform, omni_agent")
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public "
        "FROM PUBLIC, omni_platform, omni_agent"
    )

    # Remove the old two-connection role and every privilege it carried.
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM omni_reader")
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM omni_reader"
    )
    op.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM omni_reader")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT ON TABLES FROM omni_reader"
    )

    # Application procedures are unnecessary with direct platform table grants.
    for signature in (
        "omni_append_egress(text, jsonb, text, numeric, integer, integer)",
        "omni_append_ledger(text, jsonb, text, text, jsonb, jsonb)",
        "omni_bootstrap_admin(text, text)",
        "omni_claim_job()",
        "omni_finish_job(uuid, boolean, text)",
    ):
        op.execute(f"REVOKE EXECUTE ON FUNCTION {signature} FROM PUBLIC, omni_reader")
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")

    op.execute(
        "REVOKE EXECUTE ON FUNCTION omni_reject_mutation() "
        "FROM PUBLIC, omni_reader, omni_platform, omni_agent"
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public "
        "FROM omni_platform, omni_agent"
    )
    op.execute("GRANT EXECUTE ON FUNCTION omni_reject_mutation() TO omni_platform")
    op.execute("DROP ROLE IF EXISTS omni_reader")

    application_tables = tuple(build_metadata().tables)
    for table_name in application_tables:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", table_name):
            raise RuntimeError(f"Unexpected table identifier in schema: {table_name}")
        op.execute(
            f"REVOKE ALL PRIVILEGES ON TABLE public.{table_name} "
            "FROM PUBLIC, omni_platform, omni_agent"
        )

    # Platform access is explicit: all application tables are readable, while
    # only account/job rows are mutable and audit rows are insert-only.
    for table_name in application_tables:
        op.execute(f"GRANT SELECT ON TABLE public.{table_name} TO omni_platform")
    op.execute("GRANT INSERT, UPDATE, DELETE ON TABLE auth_user, job TO omni_platform")
    op.execute("GRANT INSERT ON TABLE ledger, egress_log TO omni_platform")

    entity_names = tuple(load_schema()["entities"])
    for table_name in entity_names:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", table_name):
            raise RuntimeError(f"Unexpected entity identifier in schema: {table_name}")
        op.execute(f"GRANT SELECT ON TABLE public.{table_name} TO omni_agent")
    op.execute("GRANT SELECT, INSERT ON TABLE scratch TO omni_agent")

    # Newly created tables/functions stay private; later migrations must grant
    # access explicitly. The extension routines retain their normal privileges.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE ALL ON TABLES FROM PUBLIC, omni_platform, omni_agent"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
    )

    # A database constraint closes concurrent or direct attempts to bootstrap
    # more than one administrator.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS auth_user_single_administrator
        ON auth_user (role) WHERE role = 'administrator'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS auth_user_single_administrator")
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public "
        "FROM omni_agent, omni_platform"
    )
    op.execute("DROP ROLE IF EXISTS omni_agent")
    op.execute("DROP ROLE IF EXISTS omni_platform")
    # The prior omni_reader design is intentionally not restored.
