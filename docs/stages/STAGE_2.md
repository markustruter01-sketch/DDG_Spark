# Stage 2: Synthetic organisations

> Part 1 (generator and Corvane, tasks 1–6 and 8) built 19 November 2026.
> Part 2 (Blue Team, task 7) is next.

## Goal

One command and a seed produce Corvane Group's 20-year archive as the messy
source files a real company would hand over. Eight planted problems (the
world brief's list) are hidden in it, each with an answer key, and plain code (no AI) proves each one can
be found. Then a second, smaller organisation, Blue Team, is produced from a
second configuration with no change to the generator code.

Stage 2 makes files only. Loading them into the data model is Stage 3.

## Before you start

Read `README.md`, `replit.md`, `docs/MASTER_PLAN.md`, `docs/TRUST_RULES.md`
and `docs/WORLD_BRIEF_CORVANE.md`. The Stage 1 sample generator is
`backend/spark/sim/`. Keep its command and its tests working.

## Decisions

1. **Two sizes.** `small` (default, used by tests and day-to-day work: one
   division, a handful of sites, a few hundred people) and `full` (the brief:
   about 18,500 people, about 140 sites, 14 countries). Same seed, same
   generator; the size only changes counts. `full` runs only when asked.
2. **Files, not tables.** Output goes to `generated-artifacts/<org>/<size>/`
   (already ignored by git) as the source systems would export them: CSV
   database exports, spreadsheets, free-text shift reports, and documents.
   Scanned PDFs are left to Stage 3, which owns document parsing.
3. **Mess on purpose.** Each source system carries the mess listed in the
   world brief (changed chart of accounts in 2021, duplicate people after the
   2015 HR merge, three asset coding schemes, conflicting stock counts, late
   and missing entries, renamed and closed sites). Mess is driven by the
   configuration, so the same code can produce a tidier or messier archive.
4. **Everything from configuration.** Organisation facts, source systems,
   mess and planted problems live in YAML under `backend/spark/sim/orgs/`.
   No Corvane or defence word appears in generator code.
5. **Answer keys are separate.** Each organisation's planted problems are
   defined in `orgs/<org>/problems.yaml`. The build writes the answer key
   (every planted problem, the records involved and the expected finding) to
   `generated-artifacts/<org>/<size>-answer-key.yaml`, outside the archive
   folder. Agents never read either; only evaluation does.

## Tasks

1. **Generator framework.** Reusable pieces in `backend/spark/sim/`: seeded
   random source, calendar helpers, writers for CSV and text, and a size
   setting. Same seed and size gives byte-identical files.
2. **Corvane configuration.** `backend/spark/sim/orgs/corvane/` with the
   structure, timeline and source systems from the world brief.
3. **Source systems.** One generator per source system in the world brief's
   table: finance ledgers (two generations), HR (old and new), maintenance
   (three), inventory and procurement, operations, legal and risk (text
   documents only), site register.
4. **Planted problems.** The eight in the world brief (two each for Supply
   and People, one each for the other four harnesses), written into the
   source data and recorded in the answer key.
5. **Recovery checks.** `backend/spark/sim/recover.py` finds each planted
   problem from the generated files with plain code, and reports found or not
   found against the answer key.
6. **One command.** `uv run python -m spark.sim.build --org corvane --size small`
   generates the archive and runs the recovery checks.
7. **Blue Team.** A short world brief `docs/WORLD_BRIEF_BLUE_TEAM.md`, a
   configuration under `orgs/blue_team/`, and its own planted problems. It is
   produced by the same command with `--org blue_team` and no generator code
   change. The defence pack (`backend/spark/packs/defence.yaml`) gains its
   rules.
8. **Tests.** Same seed reproduces the same files; each planted problem is
   recovered for both organisations at `small` size; generator code contains
   no organisation-specific words.

## Out of scope

Loading into the database, entity resolution, mappings, scanned PDFs, new
harnesses, AI calls, dashboard changes.

## Gate

1. `uv run python -m spark.sim.build --org corvane --size small` run twice
   with the same seed gives identical files (checksums printed).
2. The recovery checks report all eight Corvane problems found.
3. The same command with `--org blue_team` produces Blue Team and its
   recovery checks all pass, with no generator code changed between the two.
4. A search of `backend/spark/sim/*.py` finds no Corvane, defence or other
   sector-specific word.
5. `--size full` completes for Corvane; report its file count, total size
   and run time.
6. `pnpm run check` passes.
