from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from omni.db.connections import reader_session


class PostgresAuditLedger:
    def total_for_model(self, model_id: str, day: date) -> Decimal:
        query = text(
            """
            SELECT COALESCE(SUM(cost_usd), 0)
            FROM egress_log
            WHERE model = :model_id AND created_at::date = :day
            """
        )
        with reader_session() as session:
            value = session.execute(
                query, {"model_id": model_id, "day": day}
            ).scalar_one()
        return Decimal(value)

    def record(self, model_id: str, day: date, cost_usd: Decimal) -> None:
        # The append operation below is the durable spend record.
        return None

    def append(
        self,
        *,
        model_id: str,
        what_sent: dict[str, Any],
        reason: str,
        cost_usd: Decimal,
        tokens_in: int,
        tokens_out: int,
    ) -> None:
        with reader_session() as session:
            session.execute(
                text(
                    """
                    SELECT omni_append_egress(
                        :model_id, CAST(:what_sent AS jsonb), :reason,
                        :cost_usd, :tokens_in, :tokens_out
                    )
                    """
                ),
                {
                    "model_id": model_id,
                    "what_sent": json.dumps(what_sent),
                    "reason": reason,
                    "cost_usd": str(cost_usd),
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                },
            )
            session.commit()


def append_ledger(
    *,
    question: str,
    tool_calls: list[dict[str, Any]],
    model: str | None,
    answer: str | None,
    sources: list[dict[str, Any]],
    human_decision: dict[str, Any] | None = None,
) -> None:
    with reader_session() as session:
        session.execute(
            text(
                """
                SELECT omni_append_ledger(
                    :question, CAST(:tool_calls AS jsonb), :model, :answer,
                    CAST(:sources AS jsonb), CAST(:human_decision AS jsonb)
                )
                """
            ),
            {
                "question": question,
                "tool_calls": json.dumps(tool_calls),
                "model": model,
                "answer": answer,
                "sources": json.dumps(sources),
                "human_decision": (
                    json.dumps(human_decision) if human_decision is not None else None
                ),
            },
        )
        session.commit()
