# Stage 2 report: Synthetic organisations

Written by Claude, 20 November 2026. Results below were run in Claude's
workspace, not in Replit. Gate item 6 (`pnpm run check`, which includes the
database tests) runs in Replit after merge and is recorded there.

## Tasks

| Task | Status | Where |
| --- | --- | --- |
| 1. Generator framework | Done | `backend/spark/sim/common.py`, `world.py` |
| 2. Corvane configuration | Done | `backend/spark/sim/orgs/corvane/org.yaml` |
| 3. Source systems | Done | `backend/spark/sim/export.py` |
| 4. Planted problems | Done (8) | `orgs/corvane/problems.yaml`, `plant.py` |
| 5. Recovery checks | Done | `backend/spark/sim/recover.py` |
| 6. One command | Done | `uv run python -m spark.sim.build --org <name> --size small` |
| 7. Blue Team | Done | `docs/WORLD_BRIEF_BLUE_TEAM.md`, `orgs/blue_team/`, `packs/defence.yaml` |
| 8. Tests | Done | `backend/tests/test_stage2_archive.py` |

## Gate

Commands run from `backend/`.

**1. Same seed, identical files.** Each archive was built several times;
the checksum never changed. Small-size checksums:

```
Corvane Group (small): 371 files, 4.5 MB, 0.9 s
Checksum: 5d9a7b937f6874d3c8fda1ca924009bac57107b2f87235b8c71dc35596a04fea
Blue Team (small): 345 files, 4.0 MB, 0.8 s
Checksum: 88d982d3685581a079aa08b7e0e99ff8d44ed1cee292b99805947e1494535328
```

**2. All Corvane problems recovered** (`--org corvane --size small`):

```
  FOUND     part_runout              flagged 1, extra 0
  FOUND     supplier_lead_time       flagged 1, extra 0
  FOUND     certification_wave       flagged 1, extra 0
  FOUND     trade_turnover           flagged 1, extra 0
  FOUND     crew_clash               flagged 2, extra 0
  FOUND     contract_overspend       flagged 1, extra 0
  FOUND     coastal_pump_failures    flagged 1, extra 0
  FOUND     repeat_fault             flagged 1, extra 0
```

**3. Blue Team from configuration only** (`--org blue_team --size small`):

```
  FOUND     track_pad_runout         flagged 1, extra 0
  FOUND     spares_lead_time         flagged 1, extra 0
  FOUND     licence_wave             flagged 3, extra 0
  FOUND     mechanic_turnover        flagged 1, extra 0
  FOUND     recovery_clash           flagged 2, extra 0
  FOUND     garrison_overspend       flagged 1, extra 0
  FOUND     coastal_generator_failures flagged 1, extra 0
  FOUND     purifier_fault           flagged 1, extra 0
```

No generator code (`world.py`, `plant.py`, `export.py`) changed to add
Blue Team; the Corvane small checksum is the same before and after. The
recovery scoring in `recover.py` changed once: a flagged finding that is a
direct effect of a planted problem (the same lapsing licences against a
second activity at the same base; other bookings pulled into a planted
clash) now counts as that problem, not as an extra.

**4. No organisation or sector words in generator code.** Enforced by
`test_generator_code_has_no_organisation_or_sector_words` (passes).

**5. Full size.**

```
Corvane Group (full): 6909 files, 106.5 MB, 27.0 s   (8 of 8 found, 0 extra)
Blue Team (full): 3810 files, 39.8 MB, 10.4 s        (8 of 8 found, 0 extra)
```

Corvane full: 140 sites, 14 countries, about 18,500 active people,
6,000 assets.

**6. `pnpm run check`.** Not run here (needs the database). Without a
database: ruff, format and pyright clean; 41 passed, 1 skipped.

## Not done, and why

- Scanned PDFs and spreadsheets in .xlsx form: left to Stage 3, which owns
  document parsing. Emailed stock counts are CSV.
- Run times above are from Claude's workspace; Replit's will differ.

## Changed that the stage did not ask for

- Full size now uses a full-size item catalogue (numbered variants of the
  listed items), so Corvane full has 900 items, not 30.
- `docs/stages/STAGE_2.md` says eight planted problems (the world brief's
  list), not six.
