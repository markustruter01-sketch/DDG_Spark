# Omni

Omni is a web dashboard that ingests an organisation's historical data into one
connected model, then puts specialist AI agents on top that advise, predict and
explain. The AI works on a copy of the data and cannot change anything.

This is a showcase build on synthetic data. Nothing in this repository is, or
may ever be, real organisational data.

## Where things are

| Path | What it is |
| --- | --- |
| `docs/MASTER_PLAN.md` | What we are building and in what order. Start here |
| `docs/TRUST_RULES.md` | Rules no change may break |
| `docs/WORLD_BRIEF_CORVANE.md` | The fictional company the product is tested on |
| `docs/stages/` | One instruction file per build stage, with its pass/fail gate |
| `model/core.schema.yaml` | The universal data model. Defined once, here |
| `packs/` | Sector packs: labels, extra entities and rules per industry |
| `config/models.toml` | Which AI model serves each tier |
| `core/gateway/` | The only code that talks to an AI model |
| `tests/` | Automated tests. They run on a mock model and cost nothing |

## Run the tests

```
python -m unittest discover -s tests -v
```

## How the build works

1. A stage instruction in `docs/stages/` is given to the Replit Agent.
2. Replit builds the stage and pushes to this repository.
3. The work is reviewed against that stage's gate before the next stage starts.

## Where the working code is

The app is built and run in Replit. This repository currently holds the plan,
the rules, the brand assets and an early Python reference of the model
gateway. The Replit code is the source of truth for the application until the
two are connected.
