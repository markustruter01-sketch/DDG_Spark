from __future__ import annotations

import pytest

from spark.gateway.config import load_config
from spark.gateway.contracts import ModelAdapter, ModelDescription, ToolCall
from spark.gateway.mock import MockAdapter
from spark.gateway.router import RouteRequest
from spark.gateway.service import (
    MemoryEgressRecorder,
    ModelGateway,
    build_configured_gateway,
    model_description,
)
from spark.gateway.spend import MemorySpendLedger
from spark.ledger.postgres import PostgresAuditLedger


def assert_adapter_conformance(adapter: ModelAdapter) -> None:
    description = adapter.describe()
    assert description.name
    assert description.context_size > 0
    completion = adapter.complete([{"role": "user", "content": "Reply briefly."}])
    assert isinstance(completion.text, str)
    assert completion.tokens_in >= 0
    assert completion.tokens_out >= 0
    call_response = adapter.call_tools(
        [{"role": "user", "content": "Use the read tool."}],
        [
            {
                "name": "read_value",
                "description": "Read one value.",
                "input_schema": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                    "additionalProperties": False,
                },
            }
        ],
    )
    assert call_response.tokens_in >= 0
    assert call_response.tokens_out >= 0
    extraction = adapter.extract(
        "The name is Ada.",
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    )
    assert isinstance(extraction.values, dict)
    assert extraction.tokens_in >= 0
    assert extraction.tokens_out >= 0


def test_mock_adapter_conforms_to_all_four_operations() -> None:
    adapter = MockAdapter(
        ModelDescription(
            name="scripted-test-adapter",
            provider="mock",
            context_size=4096,
            supports_tools=True,
            runs_locally=True,
        ),
        scripted_replies=["A scripted reply."],
        scripted_tool_calls=[
            ToolCall(
                id="mock-call",
                name="read_value",
                arguments={"key": "value"},
            )
        ],
        scripted_extraction={"name": "Ada"},
    )

    assert_adapter_conformance(adapter)
    assert [item["operation"] for item in adapter.sent] == [
        "complete",
        "call_tools",
        "extract",
    ]


def test_live_work_tier_smoke_when_configured() -> None:
    gateway = build_configured_gateway(egress_recorder=PostgresAuditLedger())
    if not gateway.is_tier_live("work"):
        pytest.skip("No live work-tier adapter is configured.")
    result = gateway.run(
        RouteRequest(tier="work"),
        [{"role": "user", "content": "Reply with one short sentence."}],
    )
    assert result.completion.text
    assert result.completion.tokens_in >= 0
    assert result.completion.tokens_out >= 0


def test_mock_gateway_health_is_plainly_reported_without_a_live_adapter() -> None:
    config = load_config()
    adapters = {
        model.model_id: MockAdapter(model_description(model))
        for model in config.models.values()
    }
    gateway = ModelGateway(
        config=config,
        adapters=adapters,
        spend_ledger=MemorySpendLedger(),
        egress_recorder=MemoryEgressRecorder(),
    )
    if gateway.is_tier_live("work"):
        pytest.skip("A live work-tier adapter is configured in this environment.")
    assert gateway.health()["message"] == "Gateway is running on the mock model."
