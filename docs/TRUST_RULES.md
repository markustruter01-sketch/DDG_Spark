# Trust rules

These rules are the product. A change that breaks one is wrong even if every
test passes. If a task seems to require breaking one, stop and ask.

## The AI cannot change anything

1. Code reachable by an AI agent uses the read-only database connection. Only
   `ingest/` may use the writing connection.
2. Agent tools read. There is no tool that writes, deletes, sends or executes
   against the data model or any outside system.
3. Agents never receive credentials, connection strings or API keys in a
   prompt, a tool result or a log.
4. Agents may write only to their own scratch tables (drafts, scenarios,
   notes), which are separate from the data model and marked as AI-generated.
5. Advise-only is the default. Nothing above control-dial level 0 is enabled
   unless an administrator turns it on.

## One door to the model

6. Only `core/gateway/` may import a model vendor's SDK or name a model.
   Everything else asks the gateway for a tier: reason, work or bulk.
7. Every model call goes through `Gateway.run`, so it is routed, costed and
   written to the egress log.
8. Agent code makes no other outbound network calls.

## Everything is on the record

9. Every question, tool call, answer, source and human decision is appended to
   the ledger. Ledger rows are never updated or deleted.
10. Every statement an agent makes about the data links to the records it came
    from. A sentence with no source is flagged, not shown as fact.

## Data rules

11. Raw landed files are never modified.
12. Every record in the data model carries: source pointer, sensitivity label,
    the date it was true, and a confidence score.
13. Text from ingested documents is data, never instructions. Documents are
    read by a tool-less extraction call that fills a fixed form.
14. No real organisation's data, names or documents enter this repository.

## Portability rules

15. No sector-specific word, entity or rule in `core/`, `ingest/`, `api/` or
    `web/`. Sector content lives in `packs/`.
16. The data model is defined once, in `model/core.schema.yaml`. Types are
    generated from it, not written by hand.

## Proof

17. Every stage ships escape tests: the agent is told to delete, alter and send
    data, and each attempt must fail in the infrastructure, not by the model
    declining.
