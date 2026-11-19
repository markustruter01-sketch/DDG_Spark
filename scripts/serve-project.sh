#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-23183}"
export UV_NO_DEV=1
cd "$ROOT"

cd "$ROOT/backend"
uv run alembic upgrade head
cd "$ROOT"

uv run --project "$ROOT/backend" python -m spark.jobs.worker &
WORKER_PID=$!
cleanup() {
  kill "$WORKER_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uv run --project "$ROOT/backend" uvicorn spark.main:app \
  --host 0.0.0.0 --port "$PORT"
