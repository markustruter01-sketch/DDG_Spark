# Omni master plan (v2.1, repository copy)

This is the working copy for anyone building in this repository. The full
audited plan, with diagrams and reasoning, is kept alongside the project
documents; this file must stay consistent with it.

## What Omni is

A web dashboard with two parts built as one product:

1. **A data foundation** that takes in everything an organisation holds
   (databases, spreadsheets, documents, scans) and resolves it into one
   connected data model, keeping the raw originals and full lineage.
2. **A decision layer** of specialist AI agents ("harnesses") that read that
   model and advise, predict and explain. Every statement links to its
   sources. The AI cannot change anything.

It is tested on a fictional company, Corvane Group
(`docs/WORLD_BRIEF_CORVANE.md`). A fictional defence force, Blue Team, is
added later to prove the same product onboards a different sector by
configuration alone.

## Architecture, top to bottom

| Layer | Folder | Job |
| --- | --- | --- |
| Web dashboard | `web/` | 3D core, harness workspaces, evidence drawer, Trust Centre |
| API | `api/` | Sign-in, permissions, routes for the dashboard |
| Orchestrator | `core/orchestrator/` | Routes questions to harnesses, merges answers, runs scenarios |
| Harnesses | `harnesses/` | One folder per harness: data scope, tools, rules, watchlist, templates |
| Sector packs | `packs/` | Labels, extra entities and rules per industry |
| Read tools | `core/tools/` | Typed, read-only, permission-checked access to the data model |
| Data model | `model/` | The single schema; the Vault |
| Data foundation | `ingest/` | Landing, parsing, mapping, entity resolution, lineage |

Three things cut across every layer: the **model gateway** (`core/gateway/`),
the **ledger** (`core/ledger/`), and the **trust rules** (`docs/TRUST_RULES.md`).

## The six universal harnesses

| Key | Enterprise label | Depth in the showcase |
| --- | --- | --- |
| `supply_logistics` | Supply and Logistics | Deep |
| `people` | People | Deep |
| `operations` | Operations | Deep |
| `finance` | Finance | Dashboards and basic agent |
| `assets` | Assets and Infrastructure | Dashboards and basic agent |
| `risk_compliance` | Risk and Compliance | Dashboards and basic agent |

## Models

Harnesses ask the gateway for a tier. `config/models.toml` decides the model.

| Tier | Used for | Model |
| --- | --- | --- |
| reason | Orchestration, cross-harness answers, challenger | Opus 5.5; Fable 5.2 on escalation |
| work | Harness agents, briefs, mapping proposals | Sonnet 5.5 |
| bulk | Reading and extracting from many documents | Haiku 5.5 |

Fable is used only when a rule fires: the user switches on "Deep think", the
question spans three or more harnesses, the challenger disagrees with the
first answer, or the citation check fails twice. A daily budget caps it; when
the budget is spent, requests fall back to Opus and the dashboard says so.
All automated tests use the mock model.

## Stack

- **Web:** React, TypeScript, Vite, Tailwind, three.js, MapLibre.
- **Back end:** Python, FastAPI, one service organised as modules.
- **Database:** PostgreSQL for everything: data model, full-text search,
  pgvector for semantic search, PostGIS for geography.
- **Raw storage:** a write-once folder behind a storage interface.
- **Jobs:** plain Python jobs with a job table.
- **Live updates:** server-sent events.
- **Hosting:** Replit. Source of truth: this GitHub repository.

Known limits of building on Replit, stated openly: there are no containers,
so the analysis sandbox is deferred; and the block on outbound traffic from
agent code is enforced in the application, not at the network.

## Stages

Each stage has its own instruction file in `docs/stages/` and ends at a gate.
A stage is not finished until its gate passes.

| Stage | Outcome | Gate in one line |
| --- | --- | --- |
| 0 Foundations | Running empty stack, schema, themed shell | One command starts a signed-in dashboard shell; tests pass |
| 1 Walking skeleton | One question answered end to end with sources | Planted problem found with citations; escape test fails at the database |
| 2 Synthetic organisations | Corvane's 20-year archive, then Blue Team | One command and a seed reproduce the archive; planted problems recoverable |
| 3 Data foundation | Full ingestion with lineage | Archive ingests with only mapping approvals; any record opens its raw source |
| 4 AI core | Gateway, tools, harness framework, evaluation | Stage 1 agent runs as a harness folder; adapter swap is a settings change |
| 5 Harnesses | Three deep harnesses, three basic | Planted problems found at target rate; workspaces usable with AI off |
| 6 Command layer | Orchestrator, 3D core, Trust Centre | One cross-harness question answered with blockers, cost and citations |
| 7 Hardening and demo | Local model, red team, Blue Team onboarded | Two clean dry runs in front of fresh viewers |

## Feature tiers

**Must** (the demo spine): connectors for files and databases; raw landing;
catalogue; parsers; AI-proposed mappings; entity resolution; lineage; search;
read-only boundary; ledger; escape tests; gateway with three adapters and a
conformance suite; citations; evaluation suite; three deep harnesses;
sign-in and roles; 3D core with live status; harness workspaces; ask-anything
bar; evidence drawer; standard dashboards; export; forecasts with ranges.

**Should** (after Must passes its gates): self-writing connectors; privacy
gateway masking and egress view; Trust Centre; control dial levels 1 and 2;
challenger agent; overnight background agents; learning from decisions;
three basic harnesses; self-assembling organisation; time slider; generated
workspaces; voice; digital twin for Supply; Blue Team onboarding.

**Later** (designed for, not built): live system connectors; a second clock
on every fact; level 3 automation; further sector packs.

If time runs short, drop from the end of Should. Nothing in Must depends on
anything in Should.
