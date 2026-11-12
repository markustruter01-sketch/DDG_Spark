from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy import text

from omni.db.connections import reader_session

logger = logging.getLogger("omni.jobs")


def work_once() -> bool:
    with reader_session() as session:
        job = session.execute(text("SELECT * FROM omni_claim_job()")).mappings().first()
        session.commit()
    if job is None:
        return False

    message = "No Stage 0 handler is registered for this job type."
    with reader_session() as session:
        session.execute(
            text("SELECT omni_finish_job(:job_id, false, :message)"),
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
