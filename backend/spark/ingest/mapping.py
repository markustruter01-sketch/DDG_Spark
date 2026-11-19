"""Proposes how each catalogued file maps to the data model.

Rule-based: column names are matched against mapping_hints.yaml and
checked against the values (date fields need date columns, numeric fields
need numbers). The proposal says which entity the file feeds, which column
fills each field, which columns point at other entities, how confident the
rules are and why. A person approves or corrects every proposal before
anything loads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml

from spark.ingest.catalogue import CatalogueEntry
from spark.ingest.parse import parse_number

HINTS_FILE = Path(__file__).with_name("mapping_hints.yaml")
DATE_FIELDS = re.compile(r"(_on|_date|_from|_to|^as_of|_start|_end)$")
NUMBER_FIELDS = {"quantity", "amount", "cost", "unit_price", "value"}


@dataclass
class Proposal:
    path: str
    entity: str | None
    fields: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    refs: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    unmapped: list[str] = field(default_factory=lambda: list[str]())
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=lambda: list[str]())
    proposed_by: str = "rules"


@lru_cache(maxsize=1)
def load_hints() -> dict[str, dict[str, Any]]:
    return cast(
        dict[str, dict[str, Any]],
        yaml.safe_load(HINTS_FILE.read_text(encoding="utf-8")),
    )


def words(text: str) -> list[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [w for w in re.split(r"[^a-z0-9]+", spaced.lower()) if w]


def _contains(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def _column_fits(entry: CatalogueEntry, column: str, target: str) -> bool:
    if DATE_FIELDS.search(target):
        return column in entry.date_columns
    if target in NUMBER_FIELDS:
        values = [r.get(column, "") for r in entry.sample if r.get(column, "").strip()]
        return bool(values) and all(parse_number(v) is not None for v in values)
    return True


def _best_column(
    entry: CatalogueEntry, hints: list[str], target: str, taken: set[str]
) -> str | None:
    """Exact word matches first, then hints contained in a longer name."""
    for exact in (True, False):
        for hint in hints:
            hint_words = words(hint)
            for column in entry.columns:
                column_words = words(column)
                hit = (
                    column_words == hint_words
                    if exact
                    else _contains(column_words, hint_words)
                )
                if hit and column not in taken and _column_fits(entry, column, target):
                    return column
    return None


def propose(entry: CatalogueEntry) -> Proposal:
    if entry.format == "document":
        return Proposal(
            entry.path,
            "document",
            confidence=1.0,
            reasons=["Text document: stored as passages with line numbers."],
        )
    if entry.format != "table":
        return Proposal(entry.path, None, reasons=["Unknown format: needs a person."])
    path_words = words(entry.path)
    best: Proposal | None = None
    for entity, spec in load_hints().items():
        taken: set[str] = set()
        fields: dict[str, str] = {}
        refs: dict[str, str] = {}
        for target, hints in cast(dict[str, list[str]], spec.get("fields", {})).items():
            column = _best_column(entry, hints, target, taken)
            if column:
                fields[target] = column
                taken.add(column)
        for target, hints in cast(dict[str, list[str]], spec.get("refs", {})).items():
            column = _best_column(entry, hints, "ref", taken)
            if column:
                refs[target] = column
                taken.add(column)
        wanted = len(spec.get("fields", {})) + len(spec.get("refs", {}))
        coverage = (len(fields) + len(refs)) / max(wanted, 1)
        used = len(taken) / max(len(entry.columns), 1)
        named = any(
            _contains(path_words, words(w))
            for w in cast(list[str], spec.get("file", []))
        )
        own_key = entity in refs
        score = (
            0.45 * coverage
            + 0.35 * used
            + (0.12 if named else 0)
            + (0.08 if own_key else 0)
        )
        if best is None or score > best.confidence:
            reasons = [
                f"{len(fields)} fields and {len(refs)} links matched by column name"
            ]
            if named:
                reasons.append("file name suggests it")
            if own_key:
                reasons.append(f"has its own {entity} key")
            best = Proposal(
                entry.path,
                entity,
                fields,
                refs,
                [c for c in entry.columns if c not in taken],
                round(min(score, 1.0), 3),
                reasons,
            )
    assert best is not None
    return best
