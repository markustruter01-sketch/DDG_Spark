from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from spark.api.auth import ensure_admin_account
from spark.db.agent import agent_engine
from spark.db.owner import owner_engine
from spark.db.platform import platform_engine
from spark.jobs.worker import work_once
from spark.ledger.postgres import PostgresAuditLedger


def _expect_permission_error(
    engine: Engine, statement: str, parameters: dict[str, object] | None = None
) -> None:
    with pytest.raises(DBAPIError) as error:
        with engine.begin() as connection:
            connection.execute(text(statement), parameters or {})
    assert getattr(error.value.orig, "sqlstate", None) == "42501"


def _expect_database_error(engine: Engine, statement: str) -> None:
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(text(statement))


def create_test_job() -> uuid.UUID:
    job_id = uuid.uuid4()
    with platform_engine().begin() as connection:
        connection.execute(text("DELETE FROM job WHERE job_type = 'test'"))
        connection.execute(
            text(
                """
                INSERT INTO job
                  (id, job_type, payload, status, attempts, created_at)
                VALUES
                  (:id, 'test', CAST('{}' AS jsonb), 'queued', 0, now())
                """
            ),
            {"id": job_id},
        )
    return job_id


def _insert_audit_row(table: str, marker: str) -> uuid.UUID:
    row_id = uuid.uuid4()
    if table == "ledger":
        with platform_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ledger
                      (id, question, tool_calls, model, answer, sources,
                       human_decision, created_at)
                    VALUES
                      (:id, :question, '[]'::jsonb, NULL, NULL, '[]'::jsonb,
                       NULL, now())
                    """
                ),
                {"id": row_id, "question": marker},
            )
    else:
        with platform_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO egress_log
                      (id, model, what_sent, reason, cost_usd, tokens_in,
                       tokens_out, created_at)
                    VALUES
                      (:id, 'test-model', CAST(:payload AS jsonb), 'test',
                       0, 1, 1, now())
                    """
                ),
                {"id": row_id, "payload": json.dumps({"marker": marker})},
            )
    return row_id


def test_agent_connection_is_a_direct_agent_login() -> None:
    with agent_engine().connect() as connection:
        session_user, current_user = connection.execute(
            text("SELECT session_user, current_user")
        ).one()
    assert session_user == "omni_agent"
    assert current_user == "omni_agent"


def test_platform_connection_is_a_direct_platform_login() -> None:
    with platform_engine().connect() as connection:
        session_user, current_user = connection.execute(
            text("SELECT session_user, current_user")
        ).one()
    assert session_user == "omni_platform"
    assert current_user == "omni_platform"


def test_agent_reset_role_keeps_the_agent_identity() -> None:
    with agent_engine().connect() as connection:
        assert connection.execute(text("SELECT current_user")).scalar_one() == (
            "omni_agent"
        )
        connection.execute(text("RESET ROLE"))
        assert connection.execute(text("SELECT current_user")).scalar_one() == (
            "omni_agent"
        )


def test_agent_cannot_switch_to_platform_or_owner() -> None:
    with owner_engine().connect() as connection:
        owner_name = connection.execute(text("SELECT session_user")).scalar_one()
    quote = owner_engine().dialect.identifier_preparer.quote
    for statement in (
        "SET ROLE omni_platform",
        f"SET ROLE {quote(owner_name)}",
        f"SET SESSION AUTHORIZATION {quote(owner_name)}",
    ):
        _expect_permission_error(agent_engine(), statement)


@pytest.mark.parametrize(
    "table",
    [
        "auth_user",
        "job",
        "ledger",
        "egress_log",
        "source",
        "raw_record",
        "ingest_file",
        "ingest_mapping",
    ],
)
def test_agent_cannot_read_platform_or_audit_tables(table: str) -> None:
    _expect_permission_error(agent_engine(), f"SELECT * FROM public.{table} LIMIT 1")


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO public.org_unit (name) VALUES ('blocked')",
        "UPDATE public.org_unit SET name = 'blocked' WHERE false",
        "DELETE FROM public.org_unit WHERE false",
    ],
)
def test_agent_cannot_write_entity_tables(statement: str) -> None:
    _expect_permission_error(agent_engine(), statement)


def test_agent_cannot_insert_ledger_rows() -> None:
    _expect_permission_error(
        agent_engine(),
        """
        INSERT INTO public.ledger
          (id, question, tool_calls, sources, created_at)
        VALUES (gen_random_uuid(), 'blocked', '[]'::jsonb, '[]'::jsonb, now())
        """,
    )


def test_agent_cannot_run_bootstrap_or_any_remaining_procedure() -> None:
    for statement in (
        "SELECT omni_bootstrap_admin('blocked@example.invalid', 'x')",
        "SELECT omni_append_ledger('x', '[]'::jsonb, NULL, NULL, '[]'::jsonb, NULL)",
        "SELECT omni_append_egress('x', '{}'::jsonb, 'x', 0, 0, 0)",
        "SELECT omni_claim_job()",
        "SELECT omni_finish_job(gen_random_uuid(), false, 'x')",
    ):
        _expect_database_error(agent_engine(), statement)
    _expect_permission_error(agent_engine(), "SELECT omni_reject_mutation()")
    with agent_engine().connect() as connection:
        executable = (
            connection.execute(
                text(
                    """
                SELECT p.proname
                FROM pg_proc AS p
                JOIN pg_namespace AS n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                  AND p.proname LIKE 'omni_%'
                  AND has_function_privilege(current_user, p.oid, 'EXECUTE')
                """
                )
            )
            .scalars()
            .all()
        )
    assert executable == []


def test_agent_can_insert_scratch_and_read_an_entity() -> None:
    scratch_id = uuid.uuid4()
    with agent_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO scratch (id, generated_by, payload, is_ai_generated,
                                     created_at)
                VALUES (:id, 'agent-test', '{}'::jsonb, true, now())
                """
            ),
            {"id": scratch_id},
        )
        assert connection.execute(
            text("SELECT is_ai_generated FROM scratch WHERE id = :id"),
            {"id": scratch_id},
        ).scalar_one()
        assert (
            connection.execute(
                text("SELECT count(*) FROM public.org_unit")
            ).scalar_one()
            >= 0
        )
    with owner_engine().begin() as connection:
        connection.execute(
            text("DELETE FROM scratch WHERE id = :id"), {"id": scratch_id}
        )


def test_platform_can_append_to_ledger_and_egress() -> None:
    for table in ("ledger", "egress_log"):
        _insert_audit_row(table, f"platform-insert-{uuid.uuid4()}")


@pytest.mark.parametrize("table", ["ledger", "egress_log"])
def test_platform_cannot_update_or_delete_audit_rows(table: str) -> None:
    row_id = _insert_audit_row(table, f"platform-immutable-{uuid.uuid4()}")
    update_statement = (
        "UPDATE ledger SET question = 'changed' WHERE id = :id"
        if table == "ledger"
        else "UPDATE egress_log SET reason = 'changed' WHERE id = :id"
    )
    for statement in (
        update_statement,
        f"DELETE FROM {table} WHERE id = :id",
    ):
        _expect_permission_error(platform_engine(), statement, {"id": row_id})


def test_platform_cannot_change_schema_or_insert_entities() -> None:
    for statement in (
        "CREATE TABLE public.omni_forbidden_test (id integer)",
        "ALTER TABLE public.org_unit ADD COLUMN omni_forbidden_test integer",
        "DROP TABLE public.org_unit",
        "INSERT INTO public.org_unit (name) VALUES ('blocked')",
    ):
        _expect_permission_error(platform_engine(), statement)


def test_second_administrator_bootstrap_creates_nothing() -> None:
    ensure_admin_account()
    with platform_engine().connect() as connection:
        first_count = connection.execute(
            text("SELECT count(*) FROM auth_user WHERE role = 'administrator'")
        ).scalar_one()
    ensure_admin_account()
    with platform_engine().connect() as connection:
        second_count = connection.execute(
            text("SELECT count(*) FROM auth_user WHERE role = 'administrator'")
        ).scalar_one()
    assert first_count == 1
    assert second_count == first_count


def test_job_worker_claims_and_marks_unhandled_job_failed() -> None:
    job_id = create_test_job()
    assert work_once()
    with platform_engine().connect() as connection:
        status, attempts, error = connection.execute(
            text("SELECT status, attempts, error FROM job WHERE id = :job_id"),
            {"job_id": job_id},
        ).one()
    assert status == "failed"
    assert attempts == 1
    assert error


def test_job_claim_skips_a_row_locked_by_another_worker() -> None:
    job_id = create_test_job()
    claim_statement = text(
        """
        WITH next_job AS (
          SELECT id FROM job WHERE status = 'queued'
          ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
        )
        UPDATE job AS item
        SET status = 'running', attempts = attempts + 1, started_at = now()
        FROM next_job
        WHERE item.id = next_job.id
        RETURNING item.*
        """
    )
    with platform_engine().connect() as first, platform_engine().connect() as second:
        first_transaction = first.begin()
        second_transaction = second.begin()
        claimed = first.execute(claim_statement).first()
        skipped = second.execute(claim_statement).first()
        second_transaction.commit()
        first_transaction.commit()
    assert claimed is not None
    assert skipped is None
    with platform_engine().begin() as connection:
        connection.execute(
            text(
                "UPDATE job SET status = 'failed', finished_at = now() WHERE id = :id"
            ),
            {"id": job_id},
        )


def test_extensions_are_installed() -> None:
    with platform_engine().connect() as connection:
        extensions = set(
            connection.execute(text("SELECT extname FROM pg_extension")).scalars()
        )
    assert {"vector", "postgis"}.issubset(extensions)


def test_egress_log_is_the_persistent_daily_spend_ledger() -> None:
    ledger = PostgresAuditLedger()
    model_id = f"test-{uuid.uuid4()}"
    day = date.today()
    ledger.append(
        model_id=model_id,
        what_sent={"test": True},
        reason="Test call",
        cost_usd=Decimal("1.25"),
        tokens_in=1,
        tokens_out=1,
    )
    assert ledger.total_for_model(model_id, day) == Decimal("1.25")


@pytest.mark.parametrize("table", ["ledger", "egress_log"])
def test_owner_append_only_triggers_reject_update_and_delete(table: str) -> None:
    marker = str(uuid.uuid4())
    row_id = _insert_audit_row(table, marker)
    update_statement = (
        "UPDATE ledger SET question = 'changed' WHERE id = :id"
        if table == "ledger"
        else "UPDATE egress_log SET reason = 'changed' WHERE id = :id"
    )
    for statement in (
        update_statement,
        f"DELETE FROM {table} WHERE id = :id",
    ):
        with pytest.raises(DBAPIError):
            with owner_engine().begin() as connection:
                connection.execute(text(statement), {"id": row_id})
