from __future__ import annotations

from alembic import op

from omni.model.schema import build_metadata

revision = "0001_foundations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    metadata = build_metadata()
    metadata.create_all(bind=op.get_bind())

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omni_reader') THEN
            CREATE ROLE omni_reader NOLOGIN;
          END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO omni_reader")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO omni_reader")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION omni_reject_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'table is append-only';
        END
        $$;
        """
    )
    for table_name in ("raw_record", "ledger", "egress_log"):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_reject_update_delete
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION omni_reject_mutation()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_reject_truncate
            BEFORE TRUNCATE ON {table_name}
            FOR EACH STATEMENT EXECUTE FUNCTION omni_reject_mutation()
            """
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION omni_append_egress(
          p_model text, p_what_sent jsonb, p_reason text, p_cost_usd numeric,
          p_tokens_in integer, p_tokens_out integer
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        BEGIN
          INSERT INTO egress_log
            (id, model, what_sent, reason, cost_usd, tokens_in, tokens_out, created_at)
          VALUES
            (gen_random_uuid(), p_model, p_what_sent, p_reason, p_cost_usd,
             p_tokens_in, p_tokens_out, now());
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION omni_append_ledger(
          p_question text, p_tool_calls jsonb, p_model text, p_answer text,
          p_sources jsonb, p_human_decision jsonb
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        BEGIN
          INSERT INTO ledger
            (id, question, tool_calls, model, answer, sources, human_decision,
             created_at)
          VALUES
            (gen_random_uuid(), p_question, p_tool_calls, p_model, p_answer,
             p_sources, p_human_decision, now());
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION omni_bootstrap_admin(
          p_email text, p_password_hash text
        ) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        BEGIN
          INSERT INTO auth_user
            (id, email, password_hash, role, clearance, created_at)
          VALUES
            (gen_random_uuid(), p_email, p_password_hash, 'administrator',
             'restricted', now())
          ON CONFLICT (email) DO NOTHING;
          RETURN FOUND;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION omni_claim_job()
        RETURNS SETOF job
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        BEGIN
          RETURN QUERY
          WITH next_job AS (
            SELECT id FROM job WHERE status = 'queued'
            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
          )
          UPDATE job AS j
          SET status = 'running', attempts = attempts + 1, started_at = now()
          FROM next_job WHERE j.id = next_job.id
          RETURNING j.*;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION omni_finish_job(
          p_job_id uuid, p_success boolean, p_error text
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        BEGIN
          UPDATE job SET
            status = CASE WHEN p_success THEN 'done' ELSE 'failed' END,
            error = p_error,
            finished_at = now()
          WHERE id = p_job_id;
        END
        $$;
        """
    )
    op.execute(
        """
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public
        FROM omni_reader
        """
    )
    op.execute(
        """
        GRANT EXECUTE ON FUNCTION omni_append_egress(
          text, jsonb, text, numeric, integer, integer
        )
        TO omni_reader
        """
    )
    op.execute(
        """
        GRANT EXECUTE ON FUNCTION omni_append_ledger(
          text, jsonb, text, text, jsonb, jsonb
        )
        TO omni_reader
        """
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION omni_bootstrap_admin(text, text) TO omni_reader"
    )
    op.execute("GRANT EXECUTE ON FUNCTION omni_claim_job() TO omni_reader")
    op.execute(
        "GRANT EXECUTE ON FUNCTION omni_finish_job(uuid, boolean, text) TO omni_reader"
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT ON TABLES TO omni_reader
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS omni_finish_job(uuid, boolean, text)")
    op.execute("DROP FUNCTION IF EXISTS omni_claim_job()")
    op.execute("DROP FUNCTION IF EXISTS omni_bootstrap_admin(text, text)")
    op.execute(
        """
        DROP FUNCTION IF EXISTS omni_append_ledger(
          text, jsonb, text, text, jsonb, jsonb
        )
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS omni_append_egress(
          text, jsonb, text, numeric, integer, integer
        )
        """
    )
    op.execute("DROP FUNCTION IF EXISTS omni_reject_mutation()")
    build_metadata().drop_all(bind=op.get_bind())
    op.execute("DROP ROLE IF EXISTS omni_reader")
