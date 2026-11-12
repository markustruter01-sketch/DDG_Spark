# Omni Stage 0 report

**Overall:** Stage 0 is implemented in the existing React dashboard and a new Python backend. The development run button is working. The Stage 0 asset-present check and a visual check after administrator sign-in remain unverified because the owner-supplied assets are absent and the preview browser has no session.

## Stage tasks

| # | Status | Result and location |
|---|---|---|
| 1. Python backend and one run button | **Done** | Python 3.12 / uv project is in `backend/`. `artifacts/dashboard: web` runs `scripts/dev.sh`, which migrates the database and starts one FastAPI API, one PostgreSQL-backed worker and the Vite dashboard. Production uses `scripts/build-project.sh` and `scripts/serve-project.sh`; FastAPI serves the built dashboard and API. |
| 2. Universal data model and extensions | **Done** | `backend/omni/model/schema.yaml` is the sole table definition: 21 entity tables, five system tables, and the auth/job support tables. `backend/omni/model/schema.py` builds SQLAlchemy metadata from it. `backend/migrations/versions/0001_foundations.py` enables `vector` and `postgis` and creates the tables from that metadata. The running database reports both extensions installed. |
| 3. Writer and read-only reader | **Done** | `backend/omni/db/connections.py` exposes the writer and reader engines. The database allowed creation of a real `NOLOGIN` `omni_reader` role; reader connections use `SET ROLE omni_reader`. Direct insert, update and delete attempts through the reader fail in `backend/tests/test_database_guards.py`. The reader also has execute permission only on specific security-definer procedures for appending audit records, seeding the administrator, and claiming/completing jobs. It has no direct DML permission or generic mutation procedure. Migrations use the writer. |
| 4. Append-only records | **Done** | Database triggers reject update, delete and truncate on `ledger` and `egress_log`; raw landed records are also protected against mutation. Tests cover append-only behavior. The gateway appends egress through its narrow database procedure, and spend totals are read from that log. |
| 5. Model gateway | **Done** | `backend/omni/gateway/` contains the adapter contract, scripted mock adapter, tier router, TOML configuration, spend ledger and run functions. The only model identifiers are in `backend/omni/gateway/config.toml`. Reason defaults to Opus and escalates to Fable; work uses Sonnet; bulk uses Haiku. Router thresholds are three harnesses, two failed citation checks and a $5 daily escalation budget; configured prices are zero, with an optional local fallback. Tests cover all tier defaults, all four escalation rules, thresholds, budget handling, sensitivity fallback/refusal, invalid configuration, configuration-only swapping and call logging. Real provider adapters remain out of Stage 0. |
| 6. Sector packs | **Done** | `backend/omni/packs/enterprise.yaml`, `defence.yaml` and `pack-config.yaml` define both packs and the default. `OMNI_PACK` selects the active pack. The API and dashboard receive labels from the selected pack; tests cover default selection and environment-based switching. |
| 7. Sign-in, roles and clearance | **Done** | `backend/omni/api/auth.py` implements Argon2 password verification, signed sessions, administrator/analyst/viewer roles and public/internal/restricted clearances. The administrator is seeded at startup. No `OMNI_ADMIN_PASSWORD` secret was available, so a strong password was generated, only its hash was stored, and it was printed once in the first-start server log. The password is intentionally not copied into this report. |
| 8. Health, models and pack routes | **Done** | `backend/omni/api/routes.py` provides health, models, pack and authenticated SSE routes. Sign-in is public; other application routes require a session. Health was checked live; model and pack routes were tested with authenticated test dependencies. |
| 9. Night Glass design system | **Done** | `artifacts/dashboard/src/night-glass.css` and the existing shared UI components apply the Night Glass tokens, glass panels, typography, status dots, focus outline, button/card/table/tag/drawer styles and graphite dusk treatment. The mark is blended with `mix-blend-mode: screen` to avoid a black rectangle when supplied. |
| 10. Dashboard shell and 3D core | **Partly done** | The sign-in page, home shell, settings, six pack-driven workspace routes and Three.js core are in `artifacts/dashboard/src/`. The core uses white nodes and links, each node shows a hollow dot and “No data,” and it falls back to 2D when WebGL is unavailable. Reduced-motion users get a static scene. The sign-in page was visually checked; the authenticated home/settings pages were not visually captured because the preview browser has no session and the generated administrator password was not accessed. |
| 11. Owner-supplied assets | **Partly done** | `artifacts/dashboard/public/brand/` exists and `README.md` names the exact files: `ddg-loader.mp4`, `ddg-mark-glitch.png`, and `night-glass-landscape.jpg`. Runtime code handles the intro, logo and photo and falls back without an error page when a file is absent. Only the README is present, so the positive asset-present checks—video playback/skip, supplied mark appearance, home photo and dusk photo—could not be run. No brand image or video was sourced, generated, redrawn or substituted. |
| 12. Remove the Node backend and duplicate libraries | **Done, with retained metadata/tooling noted below** | Express source/package, Drizzle source/package, the generated API Zod package and generated leftovers were removed. The old API artifact directory retains only its Replit artifact metadata and has no service or workflow. Node remains enabled for the React/Vite/pnpm dashboard toolchain. |
| 13. One workspace check command | **Done** | `pnpm run check` regenerates dashboard hooks from FastAPI OpenAPI, typechecks and builds the frontend, migrates the development database, and runs Ruff, format checking, Pyright and all pytest tests. |

## Gate checks and outputs

### Run button and live API

- Workflow: `artifacts/dashboard: web`
- Run command: `bash ../../scripts/dev.sh`
- Final workflow status: `running`
- Open ports: `8080` (FastAPI) and `23183` (dashboard/Vite)
- The initial restart exposed an artifact working-directory issue: `/nix/store/1mv3qz005gkbalxfghk4y3s8ayv4d2dl-bash-interactive-5.3p15/bin/bash: scripts/dev.sh: No such file or directory`. The artifact commands were corrected to use `../../scripts/...`; the workflow then restarted successfully.

Live health and authorization smoke check:

```text
health: {"status":"ok","database":"ok","extensions":{"vector":true,"postgis":true},"gateway":{"status":"ok","adapter_count":5}}
models route without session: 401
pack route without session: 401
```

The 401 responses are expected: those routes require a session.

### Workspace gate

Command:

```text
pnpm run check
```

Commands run by `scripts/check.sh`:

```text
pnpm --filter @workspace/api-spec run codegen
pnpm run typecheck
PORT="${PORT:-5173}" BASE_PATH="${BASE_PATH:-/}" pnpm --filter @workspace/dashboard run build
cd backend
uv run alembic upgrade head
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Output:

```text
> workspace@0.0.0 check /home/runner/workspace
> bash scripts/check.sh


> @workspace/api-spec@0.0.0 codegen /home/runner/workspace/lib/api-spec
> cd ../../backend && uv run python -m omni.openapi_export --output openapi.generated.json && cd ../lib/api-spec && orval --config ./orval.config.ts && pnpm -w run typecheck:libs

🍻 orval v8.41.0 - A swagger client generator for typescript
api-client-react - Cleaning output folder
api-client-react - 🎉 Api - Your OpenAPI spec has been converted into ready to use orval!

> workspace@0.0.0 typecheck:libs /home/runner/workspace
> tsc --build


> workspace@0.0.0 typecheck /home/runner/workspace
> pnpm run typecheck:libs && pnpm -r --filter "./artifacts/**" --filter "./scripts" --if-present run typecheck


> workspace@0.0.0 typecheck:libs /home/runner/workspace
> tsc --build

Scope: 3 of 6 workspace projects
artifacts/dashboard typecheck$ tsc -p tsconfig.json --noEmit
└─ Done in 6.5s
scripts typecheck$ tsc -p tsconfig.json --noEmit
└─ Done in 3.3s
artifacts/mockup-sandbox typecheck$ tsc -p tsconfig.json --noEmit
└─ Done in 6.6s

> @workspace/dashboard@0.0.0 build /home/runner/workspace/artifacts/dashboard
> vite build --config vite.config.ts

vite v7.3.7 building client environment for production...
src/components/ui/tooltip.tsx (2:0): Error when using sourcemap for reporting an error: Can't resolve original location of error.
✓ 1775 modules transformed.
dist/public/index.html                            1.37 kB │ gzip:   0.54 kB
dist/public/assets/index-C3UjOj2W.css           105.84 kB │ gzip:  18.05 kB
dist/public/assets/index-Cd61mvAF.js            353.99 kB │ gzip: 112.90 kB
dist/public/assets/stage-zero-core-T4mIgcBD.js  523.51 kB │ gzip: 130.23 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 11.61s
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
All checks passed!
37 files already formatted
0 errors, 0 warnings, 0 informations
....................................                                     [100%]
=============================== warnings summary ===============================
../.pythonlibs/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/runner/workspace/.pythonlibs/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
36 passed, 1 warning in 3.86s
```

The command passes. It emits a source-map warning from the existing tooltip component, a Vite warning for the separately loaded Three.js chunk (523.51 kB minified; 130.23 kB gzip), and a Starlette/httpx test-client deprecation warning. Ruff passes; Pyright reports zero errors, warnings and informations.

The first check attempt failed with `Error: PORT environment variable is required but was not provided.` The check script now supplies a default build port; the final command above passes.

### Production build and static-serving configuration

Command:

```text
bash scripts/build-project.sh
```

Result: completed successfully. It synchronized only Python runtime dependencies, generated React hooks from the FastAPI OpenAPI document, and built the dashboard. The same non-fatal Vite source-map and chunk-size warnings appeared. The production run script applies Alembic migrations and starts FastAPI plus one worker; FastAPI serves the built dashboard and API.

### Route, model and pack checks

- `test_api_routes.py` verifies that `/api/models` is session-protected and returns the configured default/escalation model IDs and budget; `/api/pack` is session-protected and returns six harness labels and five entity labels from the active pack.
- Gateway tests validate the required model mapping: reason default `claude-opus-5-5`, reason escalation `claude-fable-5-2`, work `claude-sonnet-5-5`, and bulk `claude-haiku-5-5`.
- Environment-selection tests switch `OMNI_PACK` to the other YAML pack and verify the API returns its labels without dashboard-code changes. The running preview remains on the default enterprise pack.
- The sign-in page was captured in the preview with assets absent; it opens cleanly with the text-only DDG/Omni lockup. The browser reports an expected 401 from the initial session check. The authenticated core was not visually verified.

Pack labels in the YAML files:

- **Enterprise harnesses:** Supply and Logistics, People, Operations, Finance, Assets and Infrastructure, Risk and Compliance. **Entities:** Business unit, Employee, Certification, Project, Incident. Rules: stockout warning 60 days, certification expiry warning 90 days, minimum certified share 0.9, availability floor 0.85.
- **Defence harnesses:** Sustainment, Readiness and People, Operations and Plans, Finance and Capability, Fleet and Estate, Assurance. **Entities:** Unit, Member, Qualification, Operation, Report.

### Portability search

Model-name search outside the gateway and in the dashboard/tests: **no matches**. The identifiers occur only in `backend/omni/gateway/config.toml`.

Industry-term search of executable backend source and dashboard source: **no matches**. The search excludes the sector-pack YAML files, which intentionally contain sector labels, and `schema.yaml`, which contains the requested universal entities. Those names are data, not platform logic.

## Remaining limitations and reasons

1. The three owner assets are not in `artifacts/dashboard/public/brand/`; therefore the asset-present gate could not be run. Missing-file behavior was exercised by opening the dashboard without those files.
2. The preview browser does not have an administrator session. The sign-in page is visually verified and authentication/API behavior is covered by tests, but the signed-in 3D core and settings screen were not captured.
3. The first-start administrator password was generated because no `OMNI_ADMIN_PASSWORD` secret was available. It is stored only as an Argon2 hash and was printed once in the first-start server log, as requested. It is not included here.
4. Real Anthropic/OpenAI-compatible adapters and every later-stage feature remain intentionally out of scope.

## Node/backend remnants and other scope notes

- No Express API code or API workflow remains. `artifacts/api-server/.replit-artifact/artifact.toml` is retained as Replit registry metadata only; it has no service. The project’s `nodejs-24` runtime remains for the dashboard's Vite/pnpm build and development tooling.
- The old Drizzle package and generated API Zod package are removed. The separate mockup sandbox was left untouched as instructed; it retains its own Zod development dependency. Zod also remains in the lockfile as a transitive OpenAPI-generator dependency. The Omni API and dashboard client do not use the old Zod package.
- The existing workspace-wide typecheck still typechecks the mockup sandbox; its UI and workflow were not changed.
- Apart from the requested backend, API-codegen, run-button and Night Glass work, the only behavior-oriented extra was lazy-loading the 3D core so the sign-in page does not download the Three.js chunk before it is needed.
- No real organization data, model API call, image, logo or video was added.

## Publishing recommendation

**Recommended: Reserved VM.** Omni runs a persistent PostgreSQL job worker and exposes long-lived server-sent-event connections. A continuously running VM is a better fit than a scale-to-zero deployment for those processes and connections. The current workspace deployment target was not changed or published.
