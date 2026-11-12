from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from omni.db.connections import reader_engine, writer_engine
from omni.jobs.worker import work_once
from omni.ledger.postgres import PostgresAuditLedger, append_ledger


def create_test_job() -> uuid.UUID:
    job_id = uuid.uuid4()
    with writer_engine().begin() as connection:
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


def test_job_worker_claims_and_marks_unhandled_job_failed() -> None:
    job_id = create_test_job()
    assert work_once()
    with reader_engine().connect() as connection:
        status, attempts, error = connection.execute(
            text("SELECT status, attempts, error FROM job WHERE id = :job_id"),
            {"job_id": job_id},
        ).one()
    assert status == "failed"
    assert attempts == 1
    assert error


def test_job_claim_skips_a_row_locked_by_another_worker() -> None:
    job_id = create_test_job()
    with reader_engine().connect() as first, reader_engine().connect() as second:
        first_transaction = first.begin()
        second_transaction = second.begin()
        claimed = first.execute(text("SELECT * FROM omni_claim_job()")).first()
        skipped = second.execute(text("SELECT * FROM omni_claim_job()")).first()
        second_transaction.commit()
        first_transaction.commit()
    assert claimed is not None
    assert skipped is None
    with reader_engine().begin() as connection:
        connection.execute(
            text("SELECT omni_finish_job(:id, false, 'test cleanup')"),
            {"id": job_id},
        )


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO auth_user "
        "(id, email, password_hash, role, clearance, created_at) "
        "VALUES (gen_random_uuid(), 'reader-test@invalid', 'x', "
        "'viewer', 'public', now())",
        "UPDATE auth_user SET email = 'changed@invalid'",
        "DELETE FROM auth_user",
    ],
)
def test_reader_direct_insert_update_delete_fail(statement: str) -> None:
    with pytest.raises(DBAPIError):
        with reader_engine().begin() as connection:
            connection.execute(text(statement))


def test_reader_uses_database_read_only_role() -> None:
    with reader_engine().connect() as connection:
        assert connection.execute(text("SELECT current_user")).scalar_one() == (
            "omni_reader"
        )


def test_extensions_are_installed() -> None:
    with reader_engine().connect() as connection:
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


@pytest.mark.parametrize(
    ("table", "where_clause", "update_clause"),
    [
        ("ledger", "question = :marker", "question = 'changed'"),
        ("egress_log", "what_sent->>'marker' = :marker", "reason = 'changed'"),
    ],
)
def test_audit_tables_reject_update_and_delete(
    table: str,
    where_clause: str,
    update_clause: str,
) -> None:
    marker = str(uuid.uuid4())
    if table == "ledger":
        append_ledger(
            question=marker,
            tool_calls=[],
            model=None,
            answer=None,
            sources=[],
        )
    else:
        with reader_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    SELECT omni_append_egress(
                      :model, CAST(:what_sent AS jsonb), :reason, :cost, 1, 1
                    )
                    """
                ),
                {
                    "model": "test",
                    "what_sent": json.dumps({"marker": marker}),
                    "reason": "test",
                    "cost": Decimal("0"),
                },
            )
    with reader_engine().connect() as connection:
        row_id = connection.execute(
            text(f"SELECT id FROM {table} WHERE {where_clause}"),
            {"marker": marker},
        ).scalar_one()
    for statement in (
        f"UPDATE {table} SET {update_clause} WHERE id = :row_id",
        f"DELETE FROM {table} WHERE id = :row_id",
    ):
        with pytest.raises(DBAPIError):
            with writer_engine().begin() as connection:
                connection.execute(text(statement), {"row_id": row_id})
