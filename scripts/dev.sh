#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${SPARK_API_PORT:-8080}"
WEB_PORT="${PORT:-23183}"
BASE_PATH="${BASE_PATH:-/}"

cd "$ROOT/backend"
uv run alembic upgrade head
cd "$ROOT"

uv run --project "$ROOT/backend" python -m spark.jobs.worker &
WORKER_PID=$!
# Development only: no sign-in. Delete SPARK_DEV_SKIP_SIGN_IN=1 below to turn
# sign-in back on. scripts/serve-project.sh (published app) never sets it.
SPARK_DEV_SKIP_SIGN_IN=1 PORT="$API_PORT" uv run --project "$ROOT/backend" uvicorn spark.main:app \
  --host 0.0.0.0 --port "$API_PORT" &
API_PID=$!
PORT="$WEB_PORT" BASE_PATH="$BASE_PATH" \
  pnpm --filter @workspace/dashboard run dev &
WEB_PID=$!

cleanup() {
  kill "$WEB_PID" "$API_PID" "$WORKER_PID" 2>/dev/null || true
  wait "$WEB_PID" "$API_PID" "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait -n "$WEB_PID" "$API_PID" "$WORKER_PID"
