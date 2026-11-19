from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_secret: str
    admin_email: str
    admin_password: str | None


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "")
    session_secret = os.getenv("SESSION_SECRET", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")
    if not session_secret:
        raise RuntimeError("SESSION_SECRET is required.")
    return Settings(
        database_url=database_url,
        session_secret=session_secret,
        admin_email=os.getenv("SPARK_ADMIN_EMAIL", "admin@spark.local"),
        admin_password=os.getenv("SPARK_ADMIN_PASSWORD"),
    )


def dev_skip_sign_in() -> bool:
    """Development only: treat every request as the administrator.

    Set only by scripts/dev.sh (the Replit Run button); never by
    scripts/serve-project.sh. Any value other than exactly "1" keeps sign-in on.
    """
    return os.getenv("SPARK_DEV_SKIP_SIGN_IN") == "1"
