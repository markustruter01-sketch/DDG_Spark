from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from spark.db.credentials import owner_url


@lru_cache(maxsize=1)
def owner_engine() -> Engine:
    """Owner access for Alembic, ingestion, and owner-only database tests."""
    return create_engine(owner_url(), pool_pre_ping=True)
