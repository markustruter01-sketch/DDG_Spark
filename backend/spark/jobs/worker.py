from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy import text

from spark.db.platform import platform_session

logger = logging.getLogger("spark.jobs")


def work_once() -> bool:
    with platform_session() as session:
        job = (
            session.execute(
                text(
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
            )
            .mappings()
            .first()
        )
        session.commit()
    if job is None:
        return False

    message = "No Stage 0 handler is registered for this job type."
    with platform_session() as session:
        session.execute(
            text(
                """
                UPDATE job SET status = 'failed', error = :message,
                               finished_at = now()
                WHERE id = :job_id
                """
            ),
            {"job_id": UUID(str(job["id"])), "message": message},
        )
        session.commit()
    logger.info("Marked unsupported queued job as failed.")
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("PostgreSQL job worker started.")
    while True:
        try:
            if not work_once():
                time.sleep(1)
        except Exception:
            logger.exception("Job worker iteration failed.")
            time.sleep(2)


if __name__ == "__main__":
    main()
