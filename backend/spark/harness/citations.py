from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ModelStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    citations: list[str] = Field(default_factory=list)


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: list[ModelStatement]


def check_citations(
    text: str,
    returned_records: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        answer = ModelAnswer.model_validate_json(text)
    except (ValidationError, ValueError):
        fallback = text.strip() or "The model did not return a supported answer."
        return [{"text": fallback, "citations": [], "unsupported": True}], [fallback]

    statements: list[dict[str, Any]] = []
    unsupported: list[str] = []
    for statement in answer.statements:
        valid = all(record_id in returned_records for record_id in statement.citations)
        supported = bool(statement.citations) and valid
        citations = [
            {
                "entity": returned_records[record_id]["entity"],
                "record_id": record_id,
            }
            for record_id in statement.citations
            if record_id in returned_records
        ]
        if not supported:
            unsupported.append(statement.text)
        statements.append(
            {
                "text": statement.text,
                "citations": citations,
                "unsupported": not supported,
            }
        )
    return statements, unsupported


def answer_as_text(statements: list[dict[str, Any]]) -> str:
    return json.dumps(statements, ensure_ascii=False, separators=(",", ":"))
