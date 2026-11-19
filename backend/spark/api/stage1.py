from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from spark.api.auth import CurrentUser
from spark.db.platform import platform_session
from spark.gateway.service import ModelGateway
from spark.harness.loader import load_harness
from spark.harness.runner import ask_harness
from spark.model.schema import build_metadata, load_schema
from spark.packs.loader import active_pack

router = APIRouter(prefix="/api", tags=["walking-skeleton"])


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    harness_key: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=4000)
    deep_think: bool = False


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        return {key: _json_safe(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple)):
        sequence = cast(list[Any] | tuple[Any, ...], value)
        return [_json_safe(item) for item in sequence]
    return value


@router.post("/ask")
def ask(
    body: AskRequest,
    request: Request,
    user: CurrentUser,
) -> dict[str, Any]:
    pack = active_pack()
    if body.harness_key not in pack["harnesses"]:
        raise HTTPException(
            status_code=404,
            detail="That workspace is not in the active pack.",
        )
    try:
        manifest = load_harness(body.harness_key)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="That workspace is not available.",
        ) from None
    gateway: ModelGateway = request.app.state.gateway
    try:
        return ask_harness(
            gateway=gateway,
            manifest=manifest,
            user_id=str(user["user_id"]),
            question=body.question,
            deep_think=body.deep_think,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/evidence/{entity}/{record_id}")
def evidence(
    entity: str,
    record_id: UUID,
    _: CurrentUser,
) -> dict[str, Any]:
    entities = load_schema()["entities"]
    if entity not in entities:
        raise HTTPException(status_code=404, detail="Entity was not found.")
    metadata = build_metadata()
    entity_table = metadata.tables[entity]
    raw_table = metadata.tables["raw_record"]
    with platform_session() as session:
        row = (
            session.execute(select(entity_table).where(entity_table.c.id == record_id))
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Record was not found.")
        raw = (
            session.execute(select(raw_table).where(raw_table.c.id == row["source_id"]))
            .mappings()
            .first()
        )
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail="The raw source record was not found.",
        )
    return {
        "entity": entity,
        "record": jsonable_encoder(_json_safe(dict(row))),
        "raw_record": jsonable_encoder(_json_safe(dict(raw))),
    }
