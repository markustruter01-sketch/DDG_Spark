# Stage 0: Foundations

> **Done. Kept as a record.** This is the original
> instruction, written before the build. Folder names, settings and the
> two-connection design here were later changed: see `README.md`,
> `docs/MASTER_PLAN.md` and `reports/STAGE_0_REPORT.md` for what was built.

## Goal

A running, empty Omni: the database built from the schema, a signed-in web
dashboard shell in the house style, and the model gateway wired in on the
mock model. No AI features and no data yet.

## Before you start

Read `replit.md`, `docs/MASTER_PLAN.md` and `docs/TRUST_RULES.md`. The
gateway, schema, model config and packs already exist. Do not rewrite them.

## Tasks

1. **Project setup.** Python back end in `api/` using FastAPI. React,
   TypeScript, Vite and Tailwind front end in `web/`. One run command starts
   both, with the back end serving the built front end. Pin dependencies.

2. **Database.** Use Replit's PostgreSQL. Enable the `vector` and `postgis`
   extensions. If either is unavailable, stop and report it; do not work
   around it.

3. **Generate from the schema.** Write `model/generate.py`, which reads
   `model/core.schema.yaml` and produces:
   - database migrations for every entity, with the common fields on each;
   - the system tables listed in the schema (`source`, `raw_record`,
     `ledger`, `egress_log`, `scratch`);
   - Python types in `model/generated/`;
   - TypeScript types in `web/src/generated/`.
   Re-running it after a schema change must update all four.

4. **Two database connections.** `api/db.py` exposes exactly two:
   - `writer`: full access. Importable only from `ingest/` and migrations.
   - `reader`: cannot write. First try a real read-only database role. If
     the platform does not allow creating roles, open the connection with
     read-only transactions enforced, and report which approach you used.
   Add a test that an `INSERT`, `UPDATE` and `DELETE` through `reader` each
   fail with a database error.

5. **Append-only ledger.** `ledger` and `egress_log` reject `UPDATE` and
   `DELETE` at the database (trigger or rule). Add a test.

6. **Sign-in and roles.** Email and password accounts, hashed properly.
   Three roles: administrator, analyst, viewer. Each user has a clearance:
   public, internal or restricted. Seed one administrator from Replit
   Secrets. Every API route except sign-in and health requires a session.

7. **Gateway wiring.** `api/` builds one `Gateway` at start-up from
   `config/models.toml`, with `MockAdapter` registered for every model key.
   `on_call` writes each call to `egress_log`. Add
   `GET /api/models`, returning the tiers, the model behind each, and
   today's spend per model. Real model adapters are Stage 1, not now.

8. **Pack loading.** Load the pack named by an `OMNI_PACK` setting
   (default `enterprise`) and expose `GET /api/pack` with its harness and
   entity labels. The front end takes every harness name and entity name
   from this route; none are typed into front-end code.

9. **Design system.** A dark command-centre theme: near-black background,
   one accent colour, a monospace face for figures, generous spacing,
   status colours for healthy, warning and critical. Define it as Tailwind
   tokens and build these components: button, card, table, tag, status dot,
   drawer, page shell with side navigation.

10. **Dashboard shell.** After sign-in:
    - a home page with the 3D core: a three.js scene with a central node
      and one node per harness, labelled from the pack, slowly rotating,
      each clickable. All nodes show a neutral "no data yet" state;
    - an empty workspace page per harness;
    - a settings page showing the output of `/api/models` and `/api/pack`.
    The scene must hold a smooth frame rate on a laptop and fall back to a
    flat 2D layout if WebGL is unavailable.

11. **Health and tests.** `GET /api/health` reports database, extensions
    and gateway status. Add a GitHub Actions workflow that runs all Python
    tests and the front-end type check on every push.

## Out of scope for this stage

Ingestion, any real model call, harness logic, agents, the Trust Centre,
voice, charts, maps. Leave them.

## Gate

All of these must be true. Run them and paste the output in your report.

1. From a fresh clone, the documented run command starts the app with no
   manual steps beyond setting secrets.
2. `python -m unittest discover -s tests -v` passes, including the existing
   gateway tests, unchanged.
3. The read-only connection test and the append-only ledger test pass.
4. Signing in as the seeded administrator shows the 3D core with six
   harness nodes labelled from the enterprise pack.
5. Setting `OMNI_PACK=defence` and restarting changes every harness label
   in the dashboard with no code change.
6. `GET /api/models` shows reason on Opus with Fable as escalation, work on
   Sonnet and bulk on Haiku.
7. A search of `api/`, `web/`, `core/` (outside `core/gateway/`) and
   `ingest/` finds no model name and no sector-specific word.
