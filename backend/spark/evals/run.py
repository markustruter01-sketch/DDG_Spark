from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text

from spark.db.platform import platform_session
from spark.gateway.config import load_config
from spark.gateway.contracts import ModelAdapter
from spark.gateway.mock import MockAdapter
from spark.gateway.service import (
    MemoryEgressRecorder,
    ModelGateway,
    build_configured_gateway,
    model_description,
)
from spark.gateway.spend import MemorySpendLedger
from spark.harness.loader import load_harness
from spark.harness.runner import ask_harness
from spark.ledger.postgres import PostgresAuditLedger
from spark.packs.loader import active_pack

ANSWER_KEY = Path(__file__).parents[1] / "sim" / "answer_key.yaml"
EVAL_QUESTION = "Which items are projected to reach zero within 60 days, and why?"


class EvaluationEgressRecorder(MemoryEgressRecorder):
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
        super().append(
            model_id=model_id,
            what_sent=what_sent,
            reason=reason,
            cost_usd=cost_usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        PostgresAuditLedger().append(
            model_id=model_id,
            what_sent=what_sent,
            reason=reason,
            cost_usd=cost_usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )


def _harness() -> tuple[str, dict[str, Any]]:
    for key in active_pack()["harnesses"]:
        try:
            return key, load_harness(key)
        except ValueError:
            continue
    raise RuntimeError("The active pack has no Stage 1 harness.")


def _user_id() -> str:
    with platform_session() as session:
        value = session.execute(
            text(
                "SELECT id::text FROM auth_user "
                "WHERE role = 'administrator' ORDER BY created_at LIMIT 1"
            )
        ).scalar_one_or_none()
    if value is None:
        raise RuntimeError("An administrator account is required for evaluation.")
    return str(value)


def _mock_gateway(
    manifest: dict[str, Any],
) -> tuple[ModelGateway, EvaluationEgressRecorder]:
    config = load_config()
    recorder = EvaluationEgressRecorder()
    adapters: dict[str, ModelAdapter] = {
        model.model_id: MockAdapter(
            model_description(model),
            reply_factory=manifest.get("mock_reply_factory"),
            tool_call_factory=manifest.get("mock_tool_call_factory"),
        )
        for model in config.models.values()
    }
    return (
        ModelGateway(
            config=config,
            adapters=adapters,
            spend_ledger=MemorySpendLedger(),
            egress_recorder=recorder,
        ),
        recorder,
    )


def _result(
    answer: dict[str, Any],
    egress: MemoryEgressRecorder,
    answer_key: dict[str, Any],
) -> dict[str, Any]:
    statements = answer["statements"]
    text_value = " ".join(statement["text"] for statement in statements)
    dates = [
        date.fromisoformat(value)
        for value in re.findall(r"\d{4}-\d{2}-\d{2}", text_value)
    ]
    expected = answer_key["expected_runout_window"]
    earliest = date.fromisoformat(str(expected["earliest"]))
    latest = date.fromisoformat(str(expected["latest"]))
    item_found = (
        str(answer_key["critical_item_name"]).casefold() in text_value.casefold()
    )
    date_found = any(earliest <= value <= latest for value in dates)
    citations_valid = bool(statements) and all(
        statement["citations"] and not statement["unsupported"]
        for statement in statements
    )
    cost = sum((entry["cost_usd"] for entry in egress.entries), start=0)
    return {
        "result": "found" if item_found and date_found else "missed",
        "critical_item_identified": item_found,
        "runout_date_in_answer_key_window": date_found,
        "citation_validity": citations_valid,
        "model": answer["model"],
        "routing_reason": answer["routing_reason"],
        "cost_usd": str(cost),
    }


def main() -> None:
    key, manifest = _harness()
    answer_key: Any = yaml.safe_load(ANSWER_KEY.read_text(encoding="utf-8"))
    user_id = _user_id()
    gateway, recorder = _mock_gateway(manifest)
    mock_answer = ask_harness(
        gateway=gateway,
        manifest=manifest,
        user_id=user_id,
        question=EVAL_QUESTION,
        deep_think=False,
    )
    mock_result = _result(mock_answer, recorder, answer_key)
    if mock_result["result"] != "found" or not mock_result["citation_validity"]:
        raise AssertionError(f"Mock evaluation did not pass: {mock_result}")

    live_gateway = build_configured_gateway()
    live_result: dict[str, Any]
    if live_gateway.is_tier_live("work"):
        live_recorder = EvaluationEgressRecorder()
        live_gateway = build_configured_gateway(egress_recorder=live_recorder)
        try:
            live_answer = ask_harness(
                gateway=live_gateway,
                manifest=manifest,
                user_id=user_id,
                question=EVAL_QUESTION,
                deep_think=False,
            )
            live_result = _result(live_answer, live_recorder, answer_key)
        except Exception as error:
            live_result = {
                "result": "error",
                "citation_validity": False,
                "error": type(error).__name__,
            }
    else:
        live_result = {
            "result": "skipped",
            "reason": "No live work-tier adapter is configured.",
        }

    print(
        json.dumps(
            {"harness": key, "mock": mock_result, "live": live_result},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
