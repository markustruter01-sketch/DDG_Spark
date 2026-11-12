# Instructions for the Replit Agent

Read these files before changing anything, in this order:

1. `docs/MASTER_PLAN.md`: what Omni is and the stage you are in.
2. `docs/TRUST_RULES.md`: rules no change may break.
3. The current stage file in `docs/stages/`: your task and its gate.

## How to work in this repository

- **Do the current stage only.** If something belongs to a later stage, leave
  it. If the stage file is unclear or seems wrong, stop and ask.
- **Do not rewrite what exists.** `core/gateway/`, `model/core.schema.yaml`,
  `config/models.toml` and `packs/` are already written and tested. Build
  around them. If one needs changing, say why before you change it.
- **One source of truth.** The data model lives in
  `model/core.schema.yaml`. Generate tables and types from it. Never write a
  second definition by hand.
- **Models.** Only `core/gateway/` may import a model SDK or name a model.
  Everything else calls `Gateway.run` with a tier.
- **Tests come with the feature.** Tests use `MockAdapter` and must not call
  a real model or need an API key.
- **Secrets.** API keys go in Replit Secrets. Never commit a key, a
  connection string or a `.env` file.
- **Keep it small.** Prefer the smallest clear code that passes the gate.
  No speculative abstractions, no unused dependencies.
- **No real data.** Everything in this repository is synthetic.

## When you finish a stage

Report, in this order:

1. Each numbered task: done, partly done or not done, with the file paths.
2. The gate: the exact commands you ran and their output.
3. Anything you could not do, and why.
4. Anything you changed that the stage file did not ask for.

Then commit and push to GitHub. Do not start the next stage.
