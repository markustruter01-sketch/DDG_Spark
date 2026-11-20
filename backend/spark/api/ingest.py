"""Sources and Mappings: the catalogue and the approval of each file's mapping."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from spark.api.auth import CurrentUser
from spark.db.platform import platform_session
from spark.ingest.registry import (
    LOADER_FIELDS,
    MappingError,
    approve_mapping,
    siblings,
)
from spark.model.schema import build_metadata, load_schema

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class MappingVersion(BaseModel):
    version: int
    entity: str | None
    fields: dict[str, str]
    refs: dict[str, str]
    confidence: float
    reasons: list[str]
    proposed_by: str
    status: str
    decided_at: datetime | None


class SourceFile(BaseModel):
    id: UUID
    archive: str
    path: str
    source_system: str
    format: str
    records: int
    first_date: date | None
    last_date: date | None
    mapping: MappingVersion | None


class SourceFileDetail(SourceFile):
    columns: list[str]
    same_folder_files: int
    sample: list[dict[str, str]]
    history: list[MappingVersion]


class EntityFields(BaseModel):
    name: str
    fields: list[str]


class ApproveMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str = Field(min_length=1, max_length=80)
    fields: dict[str, str] = Field(default_factory=dict)
    refs: dict[str, str] = Field(default_factory=dict)
    same_folder: bool = False


def _tables() -> tuple[Any, Any]:
    metadata = build_metadata()
    return metadata.tables["ingest_file"], metadata.tables["ingest_mapping"]


def _current(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The approved mapping if there is one, otherwise the open proposal."""
    for status in ("approved", "proposed"):
        found = [m for m in history if m["status"] == status]
        if found:
            return max(found, key=lambda m: m["version"])
    return None


def _load(file_ids: list[UUID] | None = None) -> list[dict[str, Any]]:
    files, mappings = _tables()
    query = select(files).order_by(files.c.archive, files.c.path)
    if file_ids is not None:
        query = query.where(files.c.id.in_(file_ids))
    with platform_session() as session:
        rows = [dict(r) for r in session.execute(query).mappings()]
        ids = [r["id"] for r in rows]
        versions = (
            session.execute(
                select(mappings)
                .where(mappings.c.file_id.in_(ids))
                .order_by(mappings.c.version)
            )
            .mappings()
            .all()
        )
    by_file: dict[UUID, list[dict[str, Any]]] = {}
    for version in versions:
        by_file.setdefault(version["file_id"], []).append(dict(version))
    for row in rows:
        row["history"] = by_file.get(row["id"], [])
        row["mapping"] = _current(row["history"])
    return rows


@router.get("/files", response_model=list[SourceFile])
def list_files(_: CurrentUser) -> list[dict[str, Any]]:
    return _load()


def _detail(file_id: UUID) -> dict[str, Any]:
    rows = _load([file_id])
    if not rows:
        raise HTTPException(status_code=404, detail="File was not found.")
    files, _ = _tables()
    with platform_session() as session:
        rows[0]["same_folder_files"] = len(siblings(session, files, rows[0]))
    return rows[0]


@router.get("/files/{file_id}", response_model=SourceFileDetail)
def get_file(file_id: UUID, _: CurrentUser) -> dict[str, Any]:
    return _detail(file_id)


@router.get("/entities", response_model=list[EntityFields])
def entities(_: CurrentUser) -> list[dict[str, Any]]:
    tables = build_metadata().tables
    return [
        {
            "name": name,
            "fields": [
                c for c in tables[name].columns.keys() if c not in LOADER_FIELDS
            ],
        }
        for name in load_schema()["entities"]
    ]


@router.post("/files/{file_id}/mapping", response_model=SourceFileDetail)
def approve(file_id: UUID, body: ApproveMapping, user: CurrentUser) -> dict[str, Any]:
    if user["role"] != "administrator":
        raise HTTPException(
            status_code=403, detail="Only an administrator approves mappings."
        )
    try:
        approve_mapping(
            file_id,
            body.entity,
            body.fields,
            body.refs,
            UUID(user["user_id"]),
            same_folder=body.same_folder,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="File was not found.") from None
    except MappingError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _detail(file_id)
