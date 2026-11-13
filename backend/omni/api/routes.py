from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from omni.api.auth import CurrentUser
from omni.db.platform import platform_session
from omni.gateway.service import ModelGateway
from omni.packs.loader import public_pack

router = APIRouter(prefix="/api", tags=["foundation"])


class HealthResponse(BaseModel):
    status: str
    database: str
    extensions: dict[str, bool]
    gateway: dict[str, Any]


class TierStatus(BaseModel):
    model: str
    escalation_model: str | None = None


class ModelsResponse(BaseModel):
    tiers: dict[str, TierStatus]
    daily_spend_usd: dict[str, str]
    daily_escalation_budget_usd: float


class HarnessLabel(BaseModel):
    key: str
    label: str


class PackResponse(BaseModel):
    name: str
    harnesses: list[HarnessLabel]
    entities: dict[str, str]
    rules: dict[str, int | float]


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    database_status = "ok"
    extensions = {"vector": False, "postgis": False}
    try:
        with platform_session() as session:
            session.execute(text("SELECT 1"))
            installed = set(
                session.execute(text("SELECT extname FROM pg_extension")).scalars()
            )
            extensions = {
                "vector": "vector" in installed,
                "postgis": "postgis" in installed,
            }
    except Exception:
        database_status = "error"
    gateway: ModelGateway = request.app.state.gateway
    status = (
        "ok" if database_status == "ok" and all(extensions.values()) else "degraded"
    )
    return HealthResponse(
        status=status,
        database=database_status,
        extensions=extensions,
        gateway=gateway.health(),
    )


@router.get("/models", response_model=ModelsResponse)
def models(
    request: Request,
    _: CurrentUser,
) -> dict[str, Any]:
    gateway: ModelGateway = request.app.state.gateway
    return gateway.model_status()


@router.get("/pack", response_model=PackResponse)
def pack(_: CurrentUser) -> dict[str, Any]:
    return public_pack()


@router.get("/events", include_in_schema=False)
async def events(
    _: CurrentUser,
) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        while True:
            yield "event: ready\ndata: {}\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
