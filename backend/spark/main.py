from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from spark.api.auth import ensure_admin_account
from spark.api.auth import router as auth_router
from spark.api.ingest import router as ingest_router
from spark.api.routes import router as foundation_router
from spark.api.stage1 import router as stage1_router
from spark.gateway.config import load_config
from spark.gateway.service import build_configured_gateway
from spark.harness.loader import load_harness
from spark.ledger.postgres import PostgresAuditLedger
from spark.packs.loader import active_pack

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = WORKSPACE_ROOT / "artifacts" / "dashboard" / "dist" / "public"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    pack = active_pack()
    audit_ledger = PostgresAuditLedger()
    mock_hooks: dict[str, object] = {}
    for key in pack["harnesses"]:
        try:
            manifest = load_harness(key)
        except ValueError:
            continue
        mock_hooks = {
            "reply_factory": manifest.get("mock_reply_factory"),
            "tool_call_factory": manifest.get("mock_tool_call_factory"),
        }
        break
    app.state.gateway = build_configured_gateway(
        config=load_config(),
        spend_ledger=audit_ledger,
        egress_recorder=audit_ledger,
        **mock_hooks,
    )
    ensure_admin_account()
    yield


app = FastAPI(
    title="Spark API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.include_router(auth_router)
app.include_router(foundation_router)
app.include_router(stage1_router)
app.include_router(ingest_router)

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
    uvicorn.run("spark.main:app", host="0.0.0.0", port=port)
