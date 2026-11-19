"""Turns raw values and documents into typed values and passages.

Source systems disagree on formats: ISO dates and day/month/year dates,
numbers with or without thousands separators. Nothing in a document is
ever treated as an instruction; documents are split into passages with
their line numbers so every statement can point back to its source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
DATE_IN_TEXT = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b")


def parse_date(value: str) -> date | None:
    """ISO (2026-11-01) or day/month/year (01/11/2026). Anything else: None."""
    text = value.strip()
    try:
        if _ISO.match(text):
            return date.fromisoformat(text)
        if _DMY.match(text):
            return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None
    return None


def parse_number(value: str) -> float | None:
    text = value.strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class Passage:
    start_line: int
    end_line: int
    text: str


def passages(path: Path) -> list[Passage]:
    """Blank-line separated blocks, with 1-based line numbers."""
    out: list[Passage] = []
    block: list[str] = []
    start = 0
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate([*lines, ""], start=1):
        if line.strip():
            if not block:
                start = number
            block.append(line)
        elif block:
            out.append(Passage(start, number - 1, "\n".join(block)))
            block = []
    return out
