# Stage 3: Data foundation

> Draft for the owner's review. Merging this file approves the plan.

## Goal

Corvane's archive (from Stage 2) goes into the data model with nothing done
by hand except approving mappings. Every loaded record can show the exact
raw line or passage it came from. Duplicates and renamed things across the
old and new systems are matched, with reasons, and anything uncertain waits
for a person.

## Before you start

Read `README.md`, `replit.md`, `docs/MASTER_PLAN.md`, `docs/TRUST_RULES.md`
and `docs/stages/reports/STAGE_2_REPORT.md`. Stage 1's loader is
`backend/spark/ingest/loader.py`: it already lands raw files once, by
checksum, into `source` and `raw_record`, and every entity row points at its
raw record. Build on it; keep the Stage 1 path working.

## Decisions

1. **Corvane small first.** It is loaded into the Replit database by
   default. Full size is loaded only after the database's storage limit is
   checked and written down.
2. **Mappings: proposed, then approved.** For each source file, Spark
   proposes how its columns map to the data model. Code rules propose first
   (names, formats, sample values). When an AI model is connected, the
   gateway may also propose, at the `bulk` tier; its proposal is shown as
   AI-proposed. An administrator approves or corrects each file's mapping
   once, on a Mappings page. Approved mappings are versioned. Nothing loads
   from a file without an approved mapping.
3. **Text is data.** Incident reports and shift reports are stored as
   documents with their exact text and position. Nothing inside them is
   ever treated as an instruction.
4. **Matching is explained and reversible.** Every match (two people, a
   renamed site, the same pump in three systems, an old and a new account
   code) records which rule matched and its confidence. High-confidence
   matches apply automatically; the rest wait in a review queue. A match can
   be undone without reloading.
5. **The agent still sees only the 21 entity tables.** Landing, mappings,
   match decisions and the review queue are platform tables. The agent
   identity gets no access to them.
6. **Answer keys stay out.** Ingestion reads only the archive folder, never
   `*-answer-key.yaml`.

## Tasks

1. **Catalogue.** Landing records each file's source system, checksum, row
   or document count, columns, and date range. A Sources page lists them.
2. **Parsers.** CSV with both date styles and the old and new number
   formats; text documents split into passages with line numbers.
3. **Mapping proposals and approvals.** Rule-based proposals, optional
   AI proposals through the gateway, and an approval page. Tests use the
   mock model.
4. **Loading.** A job loads approved files into the entity tables. Each row
   keeps its source pointer, sensitivity, the date it became true and a
   confidence. Re-running gives the same rows (stable IDs), never duplicates.
5. **Matching.** Sites (codes, old and new names), people (worker ID,
   legacy reference, name variants), assets across the three maintenance
   systems (normalised manufacturer model and site), contracts (old and new
   references) and accounts (old and new codes). Uncertain matches go to a
   review page.
6. **Lineage.** Any record in the dashboard opens an "Open source" drawer
   showing the file, line and raw values (or the document passage).
7. **Reconciliation report.** Per file: rows landed, loaded, rejected (with
   reason) and matched.
8. **Tests.** Including: re-ingest adds nothing; every loaded row has a
   source pointer; the agent identity cannot read any new table.

## Out of scope

New harnesses, harness answers, forecasts, the 3D core, scanned PDFs,
Blue Team ingestion (that is Stage 7), full-size loading before the storage
check.

## Gate

1. Starting from an empty database: build Corvane small, approve each
   file's mapping on the Mappings page, run ingestion. No other manual step.
2. The reconciliation report balances for every file: landed = loaded +
   rejected, and every rejection has a reason.
3. For 50 random loaded records, "Open source" shows the exact raw line or
   passage (automated test plus a manual look at five).
4. Matching is scored against the generator's truth (written outside the
   archive, like the answer key): duplicate people, renamed sites and
   cross-system assets. Report precision and recall; nothing below 0.95 is
   matched automatically.
5. The Stage 2 planted problems can still be found, now from the database
   instead of the files (the same checks, reading tables).
6. Escape tests pass, including for the new tables.
7. `pnpm run check` passes.
