# Trust rules

These rules are the product. A change that breaks one is wrong even if every
test passes. If a task seems to require breaking one, stop and ask.

## Three database identities

Each is a real database login with its own credentials. No code signs in as
one and switches to another.

1. **Owner.** Migrations and ingestion only. Nothing else may import it.
2. **Platform.** The platform's own services: sign-in and sessions, the job
   worker, appending to the ledger and egress log, reading for dashboard
   pages. It can insert into the ledger and egress log but never update or
   delete them, and it cannot change the database structure or write to the
   data model.
3. **Agent.** The only connection that code reachable by an AI agent may
   hold. It can read the data model entity tables and write to its own
   scratch table. It cannot read user accounts, jobs, the ledger, the egress
   log, sources or raw records, and it can run no procedures.

New tables are private to the agent identity until explicitly granted.

## The AI cannot change anything

1. Code reachable by an AI agent holds only the agent identity.
2. Agent tools read. There is no tool that writes, deletes, sends or executes
   against the data model or any outside system.
3. Agents never receive credentials, connection strings or API keys in a
   prompt, a tool result or a log.
4. Agents may write only to the scratch table, which is separate from the
   data model and marked as AI-generated.
5. Agents never write audit entries. The platform, wrapping the agent, writes
   the ledger and egress log.
6. Advise-only is the default. Nothing above control-dial level 0 is enabled
   unless an administrator turns it on.

## One door to the model

7. Only `core/gateway/` may import a model vendor's SDK or name a model.
   Everything else asks the gateway for a tier: reason, work or bulk.
8. Every model call goes through `Gateway.run`, so it is routed, costed and
   written to the egress log.
9. Agent code makes no other outbound network calls.

## Everything is on the record

10. Every question, tool call, answer, source and human decision is appended to
   the ledger. Ledger rows are never updated or deleted.
11. Every statement an agent makes about the data links to the records it came
    from. A sentence with no source is flagged, not shown as fact.

## Data rules

12. Raw landed files are never modified.
13. Every record in the data model carries: source pointer, sensitivity label,
    the date it was true, and a confidence score.
14. Text from ingested documents is data, never instructions. Documents are
    read by a tool-less extraction call that fills a fixed form.
15. No real organisation's data, names or documents enter this repository.

## Portability rules

16. No sector-specific word, entity or rule in `core/`, `ingest/`, `api/` or
    `web/`. Sector content lives in `packs/`.
17. The data model is defined once, in `model/core.schema.yaml`. Types are
    generated from it, not written by hand.

## Proof

18. Every stage ships escape tests: the agent is told to delete, alter and send
    data, and each attempt must fail in the infrastructure, not by the model
    declining.
