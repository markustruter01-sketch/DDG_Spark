"""Shared helpers for the synthetic archive generator.

Nothing here knows about any organisation or sector. Organisations are
described in YAML under ``orgs/<name>/``.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import random
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import yaml

ORGS_DIR = Path(__file__).with_name("orgs")
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = WORKSPACE_ROOT / "generated-artifacts"
SIZES = ("small", "full")

Row = dict[str, str]


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class OrgConfig:
    key: str
    org: dict[str, Any]
    problems: list[dict[str, Any]]
    size: str

    @property
    def counts(self) -> dict[str, int]:
        return {k: int(v) for k, v in self.org["sizes"][self.size].items()}

    @property
    def as_of(self) -> date:
        return date.fromisoformat(str(self.org["as_of"]))

    @property
    def start(self) -> date:
        return date.fromisoformat(str(self.org["archive_start"]))

    @property
    def timeline(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.org["timeline"])

    def when(self, key: str) -> date:
        return date.fromisoformat(str(self.timeline[key]))


def load_org(key: str, size: str) -> OrgConfig:
    if size not in SIZES:
        raise ValueError(f"Size must be one of {', '.join(SIZES)}.")
    folder = ORGS_DIR / key
    if not (folder / "org.yaml").is_file():
        known = sorted(p.name for p in ORGS_DIR.iterdir() if p.is_dir())
        raise ValueError(f"Unknown organisation {key!r}. Known: {', '.join(known)}.")
    org = cast(dict[str, Any], load_yaml(folder / "org.yaml"))
    problems = cast(list[dict[str, Any]], load_yaml(folder / "problems.yaml") or [])
    return OrgConfig(key=key, org=org, problems=problems, size=size)


def rng(seed: int, *parts: str) -> random.Random:
    """A random source that depends only on the seed and a name."""
    label = "/".join(parts).encode("utf-8")
    return random.Random(seed * 1_000_003 + zlib.crc32(label))


def month_start(value: date) -> date:
    return value.replace(day=1)


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(index, 12)
    day = min(value.day, calendar.monthrange(year, month0 + 1)[1])
    return date(year, month0 + 1, day)


def month_end(value: date) -> date:
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def months_between(start: date, end: date) -> list[date]:
    """First day of every month from start's month to end's month."""
    out: list[date] = []
    current = month_start(start)
    while current <= end:
        out.append(current)
        current = add_months(current, 1)
    return out


def days(n: int) -> timedelta:
    return timedelta(days=n)


def weighted(randomizer: random.Random, items: Sequence[Mapping[str, Any]]) -> Any:
    weights = [float(item.get("weight", 1)) for item in items]
    return randomizer.choices(list(items), weights=weights, k=1)[0]


def dmy(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def normalise_code(value: str) -> str:
    """Upper-case letters and digits only: 'ksb eta150' -> 'KSBETA150'."""
    return "".join(ch for ch in value.upper() if ch.isalnum())


class ArchiveWriter:
    """Writes source files and keeps a checksum of everything written."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files: dict[str, str] = {}

    def _write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        self.files[relative] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    def csv(self, relative: str, header: Sequence[str], rows: Iterable[Row]) -> None:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(header), lineterminator="\n")
        writer.writeheader()
        count = 0
        for row in rows:
            writer.writerow(row)
            count += 1
        if count == 0:
            raise ValueError(f"Refusing to write an empty file: {relative}")
        self._write(relative, buffer.getvalue())

    def text(self, relative: str, body: str) -> None:
        self._write(relative, body if body.endswith("\n") else body + "\n")

    def digest(self) -> str:
        joined = "\n".join(f"{name} {self.files[name]}" for name in sorted(self.files))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def read_csv(path: Path) -> list[Row]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]
