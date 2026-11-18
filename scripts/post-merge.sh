#!/bin/bash
set -e
pnpm install --frozen-lockfile
(cd backend && uv sync --dev --locked && uv run alembic upgrade head)
