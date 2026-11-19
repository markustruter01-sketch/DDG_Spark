from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from spark.gateway.config import CONFIG_FILE, GatewayConfig, load_config
from spark.gateway.contracts import ModelDescription, ToolCall
from spark.gateway.mock import MockAdapter
from spark.gateway.router import RouteRequest, SensitivityRefused, route_request
from spark.gateway.service import MemoryEgressRecorder, ModelGateway
from spark.gateway.spend import MemorySpendLedger

TODAY = date(2026, 11, 12)


def setup_gateway() -> tuple[GatewayConfig, MemorySpendLedger]:
    return load_config(), MemorySpendLedger()


@pytest.mark.parametrize("tier_name", ["reason", "work", "bulk"])
def test_each_tier_uses_its_configured_default(tier_name: str) -> None:
    config, spend = setup_gateway()
    decision = route_request(config, RouteRequest(tier=tier_name), spend, TODAY)
    assert decision.model_key == config.tiers[tier_name].default


@pytest.mark.parametrize(
    ("route_request_case", "expected_reason"),
    [
        (
            RouteRequest(tier="reason", deep_think=True),
            "Deep think was switched on",
        ),
        (
            RouteRequest(tier="reason", harness_count=3),
            "question spans 3 harnesses (minimum 3)",
        ),
        (
            RouteRequest(tier="reason", challenger_disagreed=True),
            "challenger disagreed with the first answer",
        ),
        (
            RouteRequest(tier="reason", citation_check_failures=2),
            "Citation checks failed 2 times (threshold 2)",
        ),
    ],
)
def test_each_reason_rule_escalates(
    route_request_case: RouteRequest, expected_reason: str
) -> None:
    config, spend = setup_gateway()
    decision = route_request(config, route_request_case, spend, TODAY)
    assert decision.model_key == config.tiers["reason"].escalation
    assert expected_reason in decision.reason


def test_reason_stays_default_below_escalation_thresholds() -> None:
    config, spend = setup_gateway()
    decision = route_request(
        config,
        RouteRequest(
            tier="reason",
            harness_count=2,
            citation_check_failures=1,
        ),
        spend,
        TODAY,
    )
    assert decision.model_key == config.tiers["reason"].default
    assert "configured default" in decision.reason.lower()


def test_only_reason_tier_escalates() -> None:
    config, spend = setup_gateway()
    decision = route_request(
        config,
        RouteRequest(tier="work", deep_think=True, harness_count=6),
        spend,
        TODAY,
    )
    assert decision.model_key == config.tiers["work"].default


def test_spent_budget_keeps_reason_default() -> None:
    config, spend = setup_gateway()
    escalation = config.models[config.tiers["reason"].escalation or ""]
    spend.record(escalation.model_id, TODAY, Decimal("5.00"))
    decision = route_request(
        config, RouteRequest(tier="reason", deep_think=True), spend, TODAY
    )
    assert decision.model_key == config.tiers["reason"].default
    assert "budget" in decision.reason.lower()
    assert "deep think was switched on" in decision.reason.lower()
    assert "rule that would have fired" in decision.reason.lower()


def test_restricted_request_routes_to_local_fallback() -> None:
    config, spend = setup_gateway()
    decision = route_request(
        config, RouteRequest(tier="reason", sensitivity="restricted"), spend, TODAY
    )
    assert config.models[decision.model_key].runs_locally
    assert "local fallback" in decision.reason.lower()


def test_restricted_request_is_refused_without_local_fallback() -> None:
    config, spend = setup_gateway()
    config = replace(config, router=replace(config.router, fallback_model=None))
    with pytest.raises(SensitivityRefused):
        route_request(
            config,
            RouteRequest(tier="reason", sensitivity="restricted"),
            spend,
            TODAY,
        )


def test_configuration_rejects_undefined_model_reference() -> None:
    source = CONFIG_FILE.read_text(encoding="utf-8")
    invalid = source.replace(
        'default = "reason_default"',
        'default = "missing_entry"',
        1,
    )
    with TemporaryDirectory() as directory:
        path = Path(directory) / "config.toml"
        path.write_text(invalid, encoding="utf-8")
        with pytest.raises(ValueError, match="undefined"):
            load_config(path)


def test_model_can_be_swapped_by_configuration_only() -> None:
    source = CONFIG_FILE.read_text(encoding="utf-8")
    config = load_config()
    default_model_id = config.models[config.tiers["reason"].default].model_id
    changed = source.replace(
        f'model_id = "{default_model_id}"',
        'model_id = "replacement-id"',
        1,
    )
    with TemporaryDirectory() as directory:
        path = Path(directory) / "config.toml"
        path.write_text(changed, encoding="utf-8")
        config = load_config(path)
        gateway = ModelGateway(config=config)
    decision = gateway.route(RouteRequest(tier="reason"), TODAY)
    assert decision.model.model_id == "replacement-id"


def test_mock_adapter_describes_records_completes_tools_and_extracts() -> None:
    adapter = MockAdapter(
        description=ModelDescription(
            name="mock",
            provider="mock",
            context_size=10,
            supports_tools=True,
            runs_locally=True,
        ),
        scripted_replies=["scripted"],
        scripted_tool_calls=[
            ToolCall(id="one", name="read", arguments={"key": "value"})
        ],
        scripted_extraction={"field": "value"},
    )
    assert adapter.describe().name == "mock"
    assert adapter.complete([{"role": "user", "content": "hello"}]).text == "scripted"
    assert adapter.call_tools([], [{"name": "read"}]).calls[0].name == "read"
    assert adapter.extract("source text", {"field": "text"}).values == {
        "field": "value"
    }
    assert [item["operation"] for item in adapter.sent] == [
        "complete",
        "call_tools",
        "extract",
    ]


def test_gateway_run_records_cost_and_egress() -> None:
    config = load_config()
    spend = MemorySpendLedger()
    egress = MemoryEgressRecorder()
    adapters = {
        model.model_id: MockAdapter(
            description=ModelDescription(
                name=model.model_id,
                provider=model.provider,
                context_size=model.context_size,
                supports_tools=model.supports_tools,
                runs_locally=model.runs_locally,
            ),
            scripted_replies=["reply"],
        )
        for model in config.models.values()
    }
    gateway = ModelGateway(config, adapters, spend, egress)
    result = gateway.run(
        RouteRequest(tier="bulk"),
        [{"role": "user", "content": "question"}],
        TODAY,
    )
    assert result.completion.text == "reply"
    assert egress.entries[0]["reason"] == result.decision.reason
    assert spend.total_for_model(result.decision.model.model_id, TODAY) == Decimal("0")
