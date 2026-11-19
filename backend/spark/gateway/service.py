from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from spark.gateway.config import GatewayConfig, ModelConfig, load_config
from spark.gateway.contracts import (
    Completion,
    ExtractionResponse,
    ModelAdapter,
    ModelDescription,
    ToolResponse,
)
from spark.gateway.mock import MockAdapter
from spark.gateway.router import RouteDecision, RouteRequest, route_request
from spark.gateway.spend import MemorySpendLedger, SpendLedger, call_cost


class EgressRecorder(Protocol):
    def append(
        self,
        *,
        model_id: str,
        what_sent: dict[str, Any],
        reason: str,
        cost_usd: Decimal,
        tokens_in: int,
        tokens_out: int,
    ) -> None: ...


class MemoryEgressRecorder:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

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
        self.entries.append(
            {
                "model_id": model_id,
                "what_sent": what_sent,
                "reason": reason,
                "cost_usd": cost_usd,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            }
        )


@dataclass(frozen=True)
class GatewayResult:
    decision: RouteDecision
    completion: Completion
    cost_usd: Decimal


class ModelGateway:
    def __init__(
        self,
        config: GatewayConfig | None = None,
        adapters: dict[str, ModelAdapter] | None = None,
        spend_ledger: SpendLedger | None = None,
        egress_recorder: EgressRecorder | None = None,
    ) -> None:
        self.config = config or load_config()
        self.adapters: dict[str, ModelAdapter] = adapters or {
            model.model_id: MockAdapter(
                ModelDescription(
                    name=model.model_id,
                    provider=model.provider,
                    context_size=model.context_size,
                    supports_tools=model.supports_tools,
                    runs_locally=model.runs_locally,
                )
            )
            for model in self.config.models.values()
        }
        missing = {
            model.model_id
            for model in self.config.models.values()
            if model.model_id not in self.adapters
        }
        if missing:
            raise ValueError(
                f"No adapter registered for configured model IDs: {missing}"
            )
        self.spend_ledger = spend_ledger or MemorySpendLedger()
        self.egress_recorder = egress_recorder or MemoryEgressRecorder()

    def route(self, request: RouteRequest, today: date) -> RouteDecision:
        return route_request(self.config, request, self.spend_ledger, today)

    def run(
        self,
        request: RouteRequest,
        messages: list[dict[str, str]],
        today: date | None = None,
    ) -> GatewayResult:
        call_day = today or date.today()
        decision = self.route(request, call_day)
        adapter = self.adapters[decision.model.model_id]
        try:
            completion = adapter.complete(messages)
        except Exception:
            self._record(
                decision,
                call_day,
                {"operation": "complete", "messages": messages},
                0,
                0,
            )
            raise
        cost = call_cost(
            completion.tokens_in,
            completion.tokens_out,
            decision.model.price_input_per_million,
            decision.model.price_output_per_million,
        )
        self.spend_ledger.record(decision.model.model_id, call_day, cost)
        self.egress_recorder.append(
            model_id=decision.model.model_id,
            what_sent={"operation": "complete", "messages": messages},
            reason=decision.reason,
            cost_usd=cost,
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
        )
        return GatewayResult(decision=decision, completion=completion, cost_usd=cost)

    def run_tools(
        self,
        request: RouteRequest,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        today: date | None = None,
    ) -> tuple[RouteDecision, ToolResponse, Decimal]:
        call_day = today or date.today()
        decision = self.route(request, call_day)
        try:
            response = self.adapters[decision.model.model_id].call_tools(
                messages, tools
            )
        except Exception:
            self._record(
                decision,
                call_day,
                {"operation": "call_tools", "messages": messages, "tools": tools},
                0,
                0,
            )
            raise
        cost = self._record(
            decision,
            call_day,
            {"operation": "call_tools", "messages": messages, "tools": tools},
            response.tokens_in,
            response.tokens_out,
        )
        return decision, response, cost

    def run_extract(
        self,
        request: RouteRequest,
        document: str,
        form: dict[str, Any],
        today: date | None = None,
    ) -> tuple[RouteDecision, ExtractionResponse, Decimal]:
        call_day = today or date.today()
        decision = self.route(request, call_day)
        try:
            response = self.adapters[decision.model.model_id].extract(document, form)
        except Exception:
            self._record(
                decision,
                call_day,
                {"operation": "extract", "document": document, "form": form},
                0,
                0,
            )
            raise
        cost = self._record(
            decision,
            call_day,
            {"operation": "extract", "document": document, "form": form},
            response.tokens_in,
            response.tokens_out,
        )
        return decision, response, cost

    def _record(
        self,
        decision: RouteDecision,
        day: date,
        what_sent: dict[str, Any],
        tokens_in: int,
        tokens_out: int,
    ) -> Decimal:
        cost = call_cost(
            tokens_in,
            tokens_out,
            decision.model.price_input_per_million,
            decision.model.price_output_per_million,
        )
        self.spend_ledger.record(decision.model.model_id, day, cost)
        self.egress_recorder.append(
            model_id=decision.model.model_id,
            what_sent=what_sent,
            reason=decision.reason,
            cost_usd=cost,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return cost

    def model_status(self, today: date | None = None) -> dict[str, Any]:
        report_day = today or date.today()
        tiers: dict[str, Any] = {}
        for tier_name, tier in self.config.tiers.items():
            model = self.config.models[tier.default]
            tier_status: dict[str, Any] = {
                "model": model.model_id,
                "provider": model.provider,
                "live": self.is_live(model.model_id),
            }
            if tier.escalation:
                tier_status["escalation_model"] = self.config.models[
                    tier.escalation
                ].model_id
            tiers[tier_name] = tier_status
        from spark.gateway.providers import provider_key

        providers = [
            {
                "name": provider.name,
                "kind": provider.kind,
                "key_name": provider.key_env,
                "connected": provider.kind == "local"
                or provider_key(self.config, provider.name) is not None,
                "free_tier": provider.free_tier,
            }
            for provider in self.config.providers.values()
        ]
        spend = {
            model.model_id: str(
                self.spend_ledger.total_for_model(model.model_id, report_day)
            )
            for model in self.config.models.values()
        }
        return {
            "profile": self.config.profile,
            "providers": providers,
            "tiers": tiers,
            "daily_spend_usd": spend,
            "daily_escalation_budget_usd": (
                self.config.router.daily_escalation_budget_usd
            ),
        }

    def is_tier_live(self, tier: str) -> bool:
        if tier not in self.config.tiers:
            raise ValueError(f"Unknown gateway tier: {tier}")
        model = self.config.models[self.config.tiers[tier].default]
        return not isinstance(self.adapters[model.model_id], MockAdapter)

    def is_live(self, model_id: str) -> bool:
        return not isinstance(self.adapters.get(model_id), MockAdapter)

    def health(self) -> dict[str, Any]:
        adapter_names = sorted(
            {adapter.describe().name for adapter in self.adapters.values()}
        )
        mock_count = sum(
            isinstance(adapter, MockAdapter) for adapter in self.adapters.values()
        )
        if mock_count == len(self.adapters):
            mode = "mock"
            message = "Gateway is running on the mock model."
        elif mock_count:
            mode = "mixed"
            message = "Gateway has both mock and live model adapters."
        else:
            mode = "live"
            message = "Gateway is running on configured live model adapters."
        return {
            "status": "ok",
            "adapter_count": len(adapter_names),
            "mode": mode,
            "message": message,
        }


def build_mock_gateway() -> ModelGateway:
    return ModelGateway()


def build_configured_gateway(
    *,
    config: GatewayConfig | None = None,
    spend_ledger: SpendLedger | None = None,
    egress_recorder: EgressRecorder | None = None,
    reply_factory: Any = None,
    tool_call_factory: Any = None,
) -> ModelGateway:
    selected_config = config or load_config()
    from spark.gateway.providers import configured_adapters

    adapters = configured_adapters(
        selected_config,
        reply_factory=reply_factory,
        tool_call_factory=tool_call_factory,
    )
    return ModelGateway(
        config=selected_config,
        adapters=adapters,
        spend_ledger=spend_ledger,
        egress_recorder=egress_recorder,
    )


def model_description(model: ModelConfig) -> ModelDescription:
    return ModelDescription(
        name=model.model_id,
        provider=model.provider,
        context_size=model.context_size,
        supports_tools=model.supports_tools,
        runs_locally=model.runs_locally,
    )
