#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

uv sync --project "$ROOT/backend" --locked --no-dev
UV_NO_DEV=1 pnpm --filter @workspace/api-spec run codegen
PORT="${PORT:-23183}" BASE_PATH="${BASE_PATH:-/}" \
  pnpm --filter @workspace/dashboard run build
