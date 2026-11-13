# Omni Stage 1 report

**Overall:** Stage 1's synthetic data-to-cited-answer path is implemented and the full workspace check passes. The sample data is in the development database; the API ask/evidence flow, ledger, egress records, and scripted evaluation pass. The signed-in dashboard could not be visually checked with the owner's account because `OMNI_ADMIN_PASSWORD` is not set and the earlier generated password is unavailable. The supplied brand files are also not present, so only their missing-file behavior could be checked.

## Stage tasks

| # | Status | Result and location |
|---|---|---|
| 0. Stage 0 administrator-password follow-up | **Done** | `backend/omni/api/auth.py` now hashes `OMNI_ADMIN_PASSWORD` and updates the existing administrator through the platform identity when the secret exists. Without it, the existing account is unchanged. `backend/tests/test_auth.py` covers both cases and verifies the password is not logged. The secret is absent in this environment, so no password was changed. |
| 1. Tiny synthetic dataset | **Done** | `backend/omni/sim/dataset.yaml` defines the invented organisation, depot, 15 parts, 20 vehicles/jobs, 10 shift reports and exactly one operational issue. `backend/omni/sim/answer_key.yaml` records the expected forecast window. `backend/omni/sim/generate.py` deterministically creates five files from a fixed seed. |
| 2. Minimal, repeatable ingestion | **Done** | `backend/omni/ingest/loader.py` lands unchanged source files into the write-once raw store, records checksums/source rows/raw records, and inserts schema-driven entities with stable IDs and lineage using the owner identity. `backend/omni/sim/run.py` is the single generate-and-ingest command. The development database contains 5 sources, 240 raw records, 1 location, 1 org unit, 20 assets, 15 items, 15 stock levels, 180 stock movements, 20 maintenance jobs, 15 purchase orders, 1 supplier and 10 documents. A repeat run inserted zero rows; `test_sample_ingestion_is_idempotent` also compares database counts before and after a second ingestion. |
| 3. Read-only agent tools | **Done** | `backend/omni/tools/read_tools.py` contains typed, parameterized reads for stock history, an explainable trend forecast with a date range, items at risk, open orders, maintenance usage and document search. Results carry entity names and record IDs. Tools connect only with the agent identity; there is no write tool. |
| 4. Real adapters and conformance | **Done; live use not exercised** | `backend/omni/gateway/providers.py` implements the Anthropic SDK and OpenAI-compatible adapters within the gateway package. Startup registers live Anthropic adapters only when the required secret exists. `backend/tests/test_gateway_adapters.py` runs the four-operation adapter conformance checks against the mock; its separate live smoke test is skipped when no live work-tier adapter is configured. No provider key is configured here, so runtime and evaluation use the mock. |
| 5. First harness and bounded agent loop | **Done** | `backend/omni/harness/supply_logistics/manifest.yaml`, `instructions.md` and `templates/answer.json` declare scope, tools, instructions and output format. `backend/omni/harness/runner.py` offers only declared tools, fences document text as untrusted data and limits tool rounds. The scripted model calls the risk, forecast and order tools and does not do the arithmetic. |
| 6. Platform citation checks | **Done** | `backend/omni/harness/citations.py` accepts citations only when their record IDs were returned by a tool in the same run. Unsupported statements are marked and returned separately. The mock evaluation reports valid citations for every statement. |
| 7. Complete audit trail | **Done** | `backend/omni/ledger/postgres.py` appends the user, harness, question, tool inputs and returned record IDs, model, routing reason, answer, sources and unsupported statements using the platform identity. Gateway egress is written to the append-only egress log. The evaluation command also writes its calls to that log. |
| 8. Ask and evidence API | **Done** | `backend/omni/api/stage1.py` provides authenticated `/api/ask` and `/api/evidence/{entity}/{record_id}` routes. The API integration test uses a signed session, asks the harness, retrieves a cited entity and raw landed record, and checks the corresponding ledger row and egress entries. |
| 9. Night Glass workspace | **Partly done** | The Supply and Logistics workspace implements the question field, deep-think toggle, cited statements, unsupported status, model/routing reason, mock-mode message and citation evidence drawer in `artifacts/dashboard/src/App.tsx` and `night-glass.css`. Typecheck and production build pass. The browser screenshot verified the sign-in page and missing-asset fallback, but a signed-in browser interaction and visual citation click were not verified because no usable administrator password is available. The central 3D core was not changed. |
| 10. Escape and injection tests | **Done** | `backend/tests/test_stage1.py` verifies refusal and logging of undeclared write-sounding tools, parameterized handling of a hostile search argument, safe treatment of the injected shift-report text, denied account access for the agent, and marking an unreturned citation unsupported. |
| 11. Evaluation and unified checks | **Done** | `backend/omni/evals/run.py` is the single evaluation command. The mock identifies the planted issue, predicts a date in the answer-key window, and validates citations. The full workspace check runs OpenAPI code generation, TypeScript checks/build, migrations, Ruff, Pyright and all pytest tests. |
| Brand assets and Night Glass | **Partly done** | Runtime features use the exact filenames and missing-file fallbacks recorded in `replit.md`: the intro plays once per session and skips for reduced motion or user input; the supplied mark is kept unchanged and its black background is blended with `mix-blend-mode: screen`; the landscape is used on home and in the shared dusk treatment elsewhere. `artifacts/dashboard/public/brand/README.md` is present, but the three owner-supplied files are absent. The lockup therefore displays text without a mark, the intro skips, and pages use plain Night/Graphite grounds. No asset was sourced, generated, redrawn or substituted. Asset-present behavior remains unverified. |
| Stage rules and carried-forward notes | **Done** | `replit.md` identifies Stage 1 as the current stage, keeps Python/TypeScript and Night Glass rules, and records the three carried-forward database notes. |

## Gate checks and outputs

### One run button, API and dashboard

Configured workflow: `artifacts/dashboard: web`  
Run command: `bash ../../scripts/dev.sh`  
The workflow was restarted after implementation. It started the worker, FastAPI and Vite without manual setup:

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO:omni.jobs:PostgreSQL job worker started.
VITE v7.3.7 ready
Local: http://localhost:23183/
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

Runtime requests:

```text
GET http://localhost:8080/api/health
{"status":"ok","database":"ok","extensions":{"vector":true,"postgis":true},"gateway":{"status":"ok","adapter_count":5,"mode":"mock","message":"Gateway is running on the mock model."}}

GET http://localhost:23183/
HTTP 200 content-type text/html

GET http://localhost:8080/api/pack without a session
HTTP 401
```

The unauthenticated 401 is expected because application routes require a session. The browser screenshot showed the text-only DDG/Omni sign-in lockup. Its initial session-check 401 is expected.

### Generate and ingest; repeat without changes

Command:

```text
cd backend && uv run python -m omni.sim.run
```

Final repeat output:

```text
Generated 5 source files.
Inserted: sources=0, raw_records=0, entities=0
```

The existing development database contains:

```text
{'source': 5, 'raw_record': 240, 'location': 1, 'org_unit': 1, 'asset': 20,
 'item': 15, 'stock_level': 15, 'stock_movement': 180, 'maintenance_job': 20,
 'purchase_order': 15, 'supplier': 1, 'document': 10, 'ledger': 37,
 'egress_log': 61}
```

### Scripted answer evaluation

Command:

```text
cd backend && uv run python -m omni.evals.run
```

Output:

```json
{
  "harness": "supply_logistics",
  "mock": {
    "result": "found",
    "critical_item_identified": true,
    "runout_date_in_answer_key_window": true,
    "citation_validity": true,
    "model": "claude-sonnet-5-5",
    "routing_reason": "Selected the configured default for the work tier.",
    "cost_usd": "0.0"
  },
  "live": {
    "result": "skipped",
    "reason": "No live work-tier adapter is configured."
  }
}
```

No live model was used. The scripted forecast returns `2026-12-19`, with a range of `2026-12-19` to `2026-12-25`; the expected window is in `backend/omni/sim/answer_key.yaml`. The answer cites the stock level, the three recent movements and the open purchase order.

The API integration test also confirmed a complete ledger row for its signed-session question: 3 tool calls, 5 source records, and 0 unsupported statements. The route returned a cited record and its raw source row. Gateway calls from the evaluation and API are persisted in `egress_log`.

### Full workspace gate

Exact command:

```text
bash scripts/check.sh
```

Final output:

```text
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
└─ Done in 6.4s
artifacts/mockup-sandbox typecheck$ tsc -p tsconfig.json --noEmit
└─ Done in 6.9s
scripts typecheck$ tsc -p tsconfig.json --noEmit
└─ Done in 3s

> @workspace/dashboard@0.0.0 build /home/runner/workspace/artifacts/dashboard
> vite build --config vite.config.ts

vite v7.3.7 building client environment for production...
src/components/ui/tooltip.tsx (2:0): Error when using sourcemap for reporting an error: Can't resolve original location of error.
✓ 1775 modules transformed.
dist/public/index.html                            1.37 kB │ gzip:   0.54 kB
dist/public/assets/index-Bx8qMnDX.css           108.51 kB │ gzip:  18.56 kB
dist/public/assets/index-Dfm0THeb.js            359.07 kB │ gzip: 114.17 kB
dist/public/assets/stage-zero-core-Bu_CT1FP.js  523.51 kB │ gzip: 130.23 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit via build.chunkSizeWarningLimit.
✓ built in 10.78s
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
All checks passed!
59 files already formatted
0 errors, 0 warnings, 0 informations
.......................................................s...........      [100%]
66 passed, 1 skipped in 5.84s
```

The skipped test is the live provider smoke test; no live work-tier adapter is configured. The dashboard build's tooltip source-map and chunk-size notices are non-fatal.

### Portability search

Commands:

```text
rg -n -i 'claude-opus|claude-fable|claude-sonnet|claude-haiku|omni-local|anthropic|openai' backend/omni --glob '!**/gateway/**'
rg -n -i 'corvane|haul truck|\btruck\b|\bmining\b|\blogistics\b|\bsupply\b' backend/omni --glob '!**/gateway/**' --glob '!**/sim/dataset.yaml' --glob '!**/harness/supply_logistics/instructions.md' --glob '!**/packs/**'
rg -n -i 'claude-opus|claude-fable|claude-sonnet|claude-haiku|omni-local|anthropic|openai|corvane|haul truck|\btruck\b|\bmining\b|\blogistics\b|\bsupply\b' artifacts/dashboard/src
```

Output: no matches. Model identifiers are confined to the gateway configuration/package; sector-specific sample content and labels remain in the synthetic dataset, harness instructions and sector packs.

## Not completed or not verifiable

- **Interactive owner sign-in and signed-in visual check:** `OMNI_ADMIN_PASSWORD` is not set. Per the requested rule, startup left the existing administrator unchanged; the generated password from the earlier first start is unavailable. The Stage 0 follow-up behavior is implemented and tested, but a real owner sign-in, home-page screenshot and browser citation click could not be performed. Setting `OMNI_ADMIN_PASSWORD` in Replit Secrets and restarting will update the existing administrator password without logging it.
- **Live provider evaluation:** no `ANTHROPIC_API_KEY` is configured. The mock evaluation passed; the optional live run was skipped.
- **Positive brand-asset checks:** only `artifacts/dashboard/public/brand/README.md` is present. The intro, mark and landscape-photo behavior with the actual files could not be checked. Missing-asset behavior was verified by opening the sign-in page.

`SESSION_SECRET` has no built-in default; the application requires it and it is configured in Replit Secrets. Its value was not displayed or written.

## Scope and environment notes

- No Stage 2 work was started. The central 3D core was left as the Stage 0 placeholder.
- No unrelated product or design changes were made. API types/hooks were regenerated from FastAPI OpenAPI as part of the required check.
- No Express, Drizzle or API-side Zod implementation remains. `artifacts/api-server/.replit-artifact/artifact.toml` is retained as Replit artifact metadata only. Node/pnpm remains for React/Vite, workspace tooling and OpenAPI code generation. The existing Zod catalog entry is only used by the ignored mockup sandbox; it is not used by the Python backend.
- The deployment target was not changed; `.replit` remains `autoscale`, as directed.
