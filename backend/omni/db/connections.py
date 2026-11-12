from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, cast

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def _database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required.")
    return value


@lru_cache(maxsize=1)
def writer_engine() -> Engine:
    return create_engine(_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def reader_engine() -> Engine:
    engine = create_engine(_database_url(), pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def set_reader_role(dbapi_connection: object, _: object) -> None:
        connection = cast(Any, dbapi_connection)
        old_autocommit = connection.autocommit
        connection.autocommit = True
        try:
            cursor = connection.cursor()  # type: ignore[attr-defined]
            try:
                cursor.execute("SET ROLE omni_reader")
            finally:
                cursor.close()
        finally:
            connection.autocommit = old_autocommit

    return engine


def writer_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=writer_engine(),
        class_=Session,
        expire_on_commit=False,
    )


def reader_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=reader_engine(),
        class_=Session,
        expire_on_commit=False,
    )


@contextmanager
def reader_session() -> Generator[Session, None, None]:
    session = reader_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def writer_session() -> Generator[Session, None, None]:
    session = writer_session_factory()()
    try:
        yield session
    finally:
        session.close()
