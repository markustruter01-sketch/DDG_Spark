from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from omni.api.auth import ensure_admin_account
from omni.api.auth import router as auth_router
from omni.api.routes import router as foundation_router
from omni.gateway.config import load_config
from omni.gateway.service import ModelGateway
from omni.ledger.postgres import PostgresAuditLedger
from omni.packs.loader import active_pack

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = WORKSPACE_ROOT / "artifacts" / "dashboard" / "dist" / "public"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    active_pack()
    audit_ledger = PostgresAuditLedger()
    app.state.gateway = ModelGateway(
        config=load_config(),
        spend_ledger=audit_ledger,
        egress_recorder=audit_ledger,
    )
    ensure_admin_account()
    yield


app = FastAPI(
    title="Omni API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.include_router(auth_router)
app.include_router(foundation_router)

if PUBLIC_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=PUBLIC_DIR / "assets"),
        name="assets",
    )


@app.get("/", include_in_schema=False)
def dashboard_index() -> FileResponse:
    index_file = PUBLIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=503, detail="Dashboard build is unavailable.")
    return FileResponse(index_file)


@app.get("/{path:path}", include_in_schema=False)
def dashboard_route(path: str) -> FileResponse:
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found.")
    public_root = PUBLIC_DIR.resolve()
    candidate = (PUBLIC_DIR / path).resolve()
    if not candidate.is_relative_to(public_root):
        raise HTTPException(status_code=404, detail="Not found.")
    if candidate.is_file():
        return FileResponse(candidate)
    index_file = PUBLIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=503, detail="Dashboard build is unavailable.")
    return FileResponse(index_file)


def main() -> None:
    import os

    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("omni.main:app", host="0.0.0.0", port=port)
