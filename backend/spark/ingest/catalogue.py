"""Describes every file in a landed archive before anything is loaded.

One entry per file: which source system it came from, its checksum, how
many rows or passages it holds, its columns and the dates it covers.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from spark.ingest.parse import DATE_IN_TEXT, parse_date, passages

TEXT_SUFFIXES = {".txt"}
TABLE_SUFFIXES = {".csv"}


@dataclass
class CatalogueEntry:
    path: str
    source_system: str
    format: str
    checksum: str
    records: int
    columns: list[str] = field(default_factory=lambda: list[str]())
    date_columns: list[str] = field(default_factory=lambda: list[str]())
    first_date: date | None = None
    last_date: date | None = None
    sample: list[dict[str, str]] = field(default_factory=lambda: list[dict[str, str]]())


def catalogue(root: Path) -> list[CatalogueEntry]:
    entries: list[CatalogueEntry] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        system = relative.split("/", 1)[0] if "/" in relative else "unsorted"
        if suffix in TABLE_SUFFIXES:
            entries.append(_table(path, relative, system, checksum))
        elif suffix in TEXT_SUFFIXES:
            entries.append(_text(path, relative, system, checksum))
        else:
            entries.append(CatalogueEntry(relative, system, "unknown", checksum, 0))
    return entries


def _table(path: Path, relative: str, system: str, checksum: str) -> CatalogueEntry:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    date_columns: list[str] = []
    seen: list[date] = []
    for column in columns:
        values = [r[column] for r in rows if r.get(column, "").strip()]
        parsed = [parse_date(v) for v in values]
        if values and all(d is not None for d in parsed):
            date_columns.append(column)
            seen.extend(d for d in parsed if d is not None)
    return CatalogueEntry(
        relative,
        system,
        "table",
        checksum,
        len(rows),
        columns,
        date_columns,
        min(seen) if seen else None,
        max(seen) if seen else None,
        rows[:20],
    )


def _text(path: Path, relative: str, system: str, checksum: str) -> CatalogueEntry:
    blocks = passages(path)
    found = [
        d
        for b in blocks
        for match in DATE_IN_TEXT.findall(b.text)
        if (d := parse_date(match)) is not None
    ]
    return CatalogueEntry(
        relative,
        system,
        "document",
        checksum,
        len(blocks),
        first_date=min(found) if found else None,
        last_date=max(found) if found else None,
    )
