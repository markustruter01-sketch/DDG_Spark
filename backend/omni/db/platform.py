from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from omni.db.credentials import service_url


@lru_cache(maxsize=1)
def platform_engine() -> Engine:
    return create_engine(service_url("omni_platform"), pool_pre_ping=True)


def platform_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=platform_engine(),
        class_=Session,
        expire_on_commit=False,
    )


@contextmanager
def platform_session() -> Generator[Session, None, None]:
    session = platform_session_factory()()
    try:
        yield session
    finally:
        session.close()
