from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from spark.db.credentials import service_url


@lru_cache(maxsize=1)
def agent_engine() -> Engine:
    return create_engine(service_url("omni_agent"), pool_pre_ping=True)


def agent_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=agent_engine(),
        class_=Session,
        expire_on_commit=False,
    )


@contextmanager
def agent_session() -> Generator[Session, None, None]:
    session = agent_session_factory()()
    try:
        yield session
    finally:
        session.close()
