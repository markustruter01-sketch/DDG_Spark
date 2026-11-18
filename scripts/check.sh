#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pnpm --filter @workspace/api-spec run codegen
pnpm run typecheck
PORT="${PORT:-5173}" BASE_PATH="${BASE_PATH:-/}" \
  pnpm --filter @workspace/dashboard run build

cd "$ROOT/backend"
uv run alembic upgrade head
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
