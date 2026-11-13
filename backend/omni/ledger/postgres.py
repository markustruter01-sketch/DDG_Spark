from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from omni.db.platform import platform_session


class PostgresAuditLedger:
    def total_for_model(self, model_id: str, day: date) -> Decimal:
        query = text(
            """
            SELECT COALESCE(SUM(cost_usd), 0)
            FROM egress_log
            WHERE model = :model_id AND created_at::date = :day
            """
        )
        with platform_session() as session:
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
        with platform_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO egress_log
                      (id, model, what_sent, reason, cost_usd, tokens_in,
                       tokens_out, created_at)
                    VALUES
                      (:id, :model_id, CAST(:what_sent AS jsonb), :reason,
                       :cost_usd, :tokens_in, :tokens_out, now())
                    """
                ),
                {
                    "id": uuid4(),
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
    with platform_session() as session:
        session.execute(
            text(
                """
                INSERT INTO ledger
                  (id, question, tool_calls, model, answer, sources,
                   human_decision, created_at)
                VALUES
                  (:id, :question, CAST(:tool_calls AS jsonb), :model, :answer,
                   CAST(:sources AS jsonb), CAST(:human_decision AS jsonb), now())
                """
            ),
            {
                "id": uuid4(),
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
