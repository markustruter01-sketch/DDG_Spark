# Spark

Spark is a Digital Dynamics Group (DDG) web dashboard. It takes in an
organisation's historical data (databases, spreadsheets, documents, scans)
into one connected model, then puts specialist AI agents on top that advise,
predict and explain. Every statement links to its sources. The AI works on a
copy of the data and cannot change anything.

This is a showcase build on synthetic data. Nothing in this repository is, or
may ever be, real organisational data.

Spark was called Omni until 19 November 2026. Database-side names still say
`omni` on purpose; `replit.md` lists them and says why.

## Where things are

| Path | What it is |
| --- | --- |
| `docs/MASTER_PLAN.md` | What we are building and in what order. Start here |
| `docs/TRUST_RULES.md` | Rules no change may break |
| `docs/WORLD_BRIEF_CORVANE.md` | The fictional company Spark is tested on |
| `docs/stages/` | One instruction file per stage, with its gate; `reports/` holds finished stage reports |
| `replit.md` | Rules the Replit agent follows, the current stage, and the Night Glass brand |
| `backend/spark/` | The Python app: API, database logins, AI gateway, agents, ingestion, ledger |
| `backend/spark/model/schema.yaml` | The data model. Defined once, here |
| `backend/spark/packs/` | Sector packs: labels and rules per industry |
| `backend/spark/gateway/` | The only code that talks to an AI model; `config.toml` picks the model for each tier |
| `backend/migrations/` | Database changes, in order |
| `backend/tests/` | Python tests. They use a mock model and cost nothing |
| `artifacts/dashboard/` | The web dashboard (React, TypeScript); brand files in `public/brand/` |
| `lib/` | The dashboard's API client, generated from the backend |
| `scripts/` | Run, build and check scripts |

`artifacts/` also holds two folders Replit's own tools need: `mockup-sandbox/`
(Replit's design canvas) and `api-server/` (old Replit metadata, no code).

## Run and check

- In Replit, the Run button starts the database migrations, the API, the job
  worker and the dashboard (`scripts/dev.sh`).
- Full check, needs the database: `pnpm run check`.
- Quick check, no database needed. GitHub runs this on every push:

```
cd backend
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest --ignore=tests/test_auth.py --ignore=tests/test_database_guards.py --ignore=tests/test_stage1.py
```

## How the build works

1. GitHub `main` is the master copy. Replit works from `main`.
2. Each stage has an instruction file in `docs/stages/` and ends at a gate.
3. Changes go on a branch, then a pull request into `main`. The quick check
   must pass.
4. Replit pulls `main` and runs the full check. A stage is done when its gate
   passes.
