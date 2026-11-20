"""Keeps the catalogue and its mappings in the database.

register_archive() records every file in an archive folder once (by path and
checksum) and stores the rule-based proposal as mapping version 1.
approve_mapping() records a person's approved or corrected mapping as a new
version; the database allows only one approved mapping per file. Nothing is
loaded into the entity tables here: loading needs an approved mapping and
comes in a later step.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from spark.db.platform import platform_session
from spark.ingest.catalogue import catalogue
from spark.ingest.mapping import propose
from spark.model.schema import build_metadata, load_schema

# Fields every entity row gets from loading, never from a source column.
LOADER_FIELDS = {"id", "source_id", "sensitivity", "confidence"}


class MappingError(ValueError):
    """A submitted mapping does not fit the file or the data model."""


def _tables() -> tuple[Any, Any]:
    metadata = build_metadata()
    return metadata.tables["ingest_file"], metadata.tables["ingest_mapping"]


def file_id(archive: str, path: str, checksum: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"spark:ingest_file:{archive}:{path}:{checksum}")


def register_archive(root: Path, archive: str) -> dict[str, int]:
    """Catalogue a folder and store new files with a proposed mapping."""
    files, mappings = _tables()
    entries = catalogue(root)
    if any("answer-key" in e.path for e in entries):
        raise RuntimeError("An answer key is inside the archive folder.")
    now = datetime.now(UTC)
    added = 0
    with platform_session() as session, session.begin():
        for entry in entries:
            new_id = file_id(archive, entry.path, entry.checksum)
            inserted = session.execute(
                pg_insert(files)
                .values(
                    id=new_id,
                    archive=archive,
                    path=entry.path,
                    source_system=entry.source_system,
                    format=entry.format,
                    checksum=entry.checksum,
                    records=entry.records,
                    columns=entry.columns,
                    date_columns=entry.date_columns,
                    first_date=entry.first_date,
                    last_date=entry.last_date,
                    sample=entry.sample,
                    catalogued_at=now,
                )
                .on_conflict_do_nothing()
                .returning(files.c.id)
            ).first()
            if inserted is None:
                continue
            added += 1
            proposal = propose(entry)
            session.execute(
                mappings.insert().values(
                    id=uuid4(),
                    file_id=new_id,
                    version=1,
                    entity=proposal.entity,
                    fields=proposal.fields,
                    refs=proposal.refs,
                    confidence=proposal.confidence,
                    reasons=proposal.reasons,
                    proposed_by=proposal.proposed_by,
                    status="proposed",
                    created_at=now,
                )
            )
    return {"files": len(entries), "added": added}


def _latest(session: Session, mappings: Any, fid: UUID, status: str) -> Any:
    return (
        session.execute(
            select(mappings)
            .where(mappings.c.file_id == fid, mappings.c.status == status)
            .order_by(mappings.c.version.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )


def validate_mapping(
    columns: list[str], entity: str, fields: dict[str, str], refs: dict[str, str]
) -> None:
    entities = load_schema()["entities"]
    if entity not in entities:
        raise MappingError(f"'{entity}' is not an entity in the data model.")
    allowed = set(build_metadata().tables[entity].columns.keys()) - LOADER_FIELDS
    bad_fields = sorted(set(fields) - allowed)
    if bad_fields:
        raise MappingError(f"Not fields of {entity}: {', '.join(bad_fields)}.")
    bad_refs = sorted(set(refs) - set(entities))
    if bad_refs:
        raise MappingError(f"Not entities: {', '.join(bad_refs)}.")
    used = [*fields.values(), *refs.values()]
    missing = sorted(set(used) - set(columns))
    if missing:
        raise MappingError(f"Not columns in this file: {', '.join(missing)}.")
    if len(used) != len(set(used)):
        raise MappingError("A column is used more than once.")


def _folder(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def siblings(session: Session, files: Any, file_row: Any) -> list[Any]:
    """Other files in the same folder with the same format and columns."""
    rows = session.execute(
        select(files).where(
            files.c.archive == file_row["archive"],
            files.c.format == file_row["format"],
            files.c.id != file_row["id"],
        )
    ).mappings()
    return [
        r
        for r in rows
        if _folder(r["path"]) == _folder(file_row["path"])
        and r["columns"] == file_row["columns"]
    ]


def _approve_one(
    session: Session,
    mappings: Any,
    fid: UUID,
    entity: str,
    fields: dict[str, str],
    refs: dict[str, str],
    user_id: UUID,
    now: datetime,
) -> None:
    proposal = _latest(session, mappings, fid, "proposed")
    unchanged = proposal is not None and (
        proposal["entity"],
        proposal["fields"],
        proposal["refs"],
    ) == (entity, fields, refs)
    version = (
        session.execute(
            select(func.max(mappings.c.version)).where(mappings.c.file_id == fid)
        ).scalar_one()
        or 0
    ) + 1
    session.execute(
        update(mappings)
        .where(
            mappings.c.file_id == fid,
            mappings.c.status.in_(("proposed", "approved")),
        )
        .values(status="superseded")
    )
    kept = proposal if unchanged else None
    session.execute(
        mappings.insert().values(
            id=uuid4(),
            file_id=fid,
            version=version,
            entity=entity,
            fields=fields,
            refs=refs,
            confidence=kept["confidence"] if kept else 1.0,
            reasons=kept["reasons"] if kept else ["Corrected by a person."],
            proposed_by=kept["proposed_by"] if kept else "person",
            status="approved",
            decided_by=user_id,
            decided_at=now,
            created_at=now,
        )
    )


def approve_mapping(
    fid: UUID,
    entity: str,
    fields: dict[str, str],
    refs: dict[str, str],
    user_id: UUID,
    same_folder: bool = False,
) -> list[UUID]:
    """Store an approved mapping as a new version and supersede older ones.

    With same_folder, the same mapping is approved for every other file in
    the folder that has the same format and columns. Returns the file IDs.
    """
    files, mappings = _tables()
    now = datetime.now(UTC)
    with platform_session() as session, session.begin():
        file_row = (
            session.execute(select(files).where(files.c.id == fid)).mappings().first()
        )
        if file_row is None:
            raise LookupError("File was not found.")
        validate_mapping(list(file_row["columns"]), entity, fields, refs)
        targets = [fid]
        if same_folder:
            targets += [r["id"] for r in siblings(session, files, file_row)]
        # Lock in a fixed order so two approvals cannot deadlock.
        session.execute(
            select(files.c.id)
            .where(files.c.id.in_(targets))
            .order_by(files.c.id)
            .with_for_update()
        ).all()
        for target in targets:
            _approve_one(session, mappings, target, entity, fields, refs, user_id, now)
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="archive folder to catalogue")
    parser.add_argument("--archive", required=True, help="name stored with each file")
    args = parser.parse_args()
    print(register_archive(args.folder, args.archive))


if __name__ == "__main__":
    main()
