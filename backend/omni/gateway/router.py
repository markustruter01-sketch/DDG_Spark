from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from omni.gateway.config import (
    SENSITIVITY_LEVELS,
    GatewayConfig,
    ModelConfig,
)
from omni.gateway.spend import SpendLedger


@dataclass(frozen=True)
class RouteRequest:
    tier: str
    sensitivity: str = "internal"
    deep_think: bool = False
    harness_count: int = 0
    challenger_disagreed: bool = False
    citation_check_failures: int = 0


@dataclass(frozen=True)
class RouteDecision:
    tier: str
    model_key: str
    model: ModelConfig
    reason: str


class SensitivityRefused(ValueError):
    """Raised when no configured model can safely receive the request."""


def route_request(
    config: GatewayConfig,
    request: RouteRequest,
    spend_ledger: SpendLedger,
    today: date,
) -> RouteDecision:
    if request.tier not in config.tiers:
        raise ValueError(f"Unknown gateway tier: {request.tier}")
    if request.sensitivity not in SENSITIVITY_LEVELS:
        raise ValueError("Request sensitivity is invalid.")

    tier = config.tiers[request.tier]
    model_key = tier.default
    reason = f"Selected the configured default for the {request.tier} tier."

    should_escalate = (
        request.tier == "reason"
        and tier.escalation is not None
        and any(
            (
                request.deep_think,
                request.harness_count >= config.router.minimum_harnesses,
                request.challenger_disagreed,
                request.citation_check_failures >= config.router.citation_failures,
            )
        )
    )
    if should_escalate and tier.escalation:
        escalation_model = config.models[tier.escalation]
        spent = spend_ledger.total_for_model(escalation_model.model_id, today)
        if spent >= Decimal(str(config.router.daily_escalation_budget_usd)):
            reason = (
                "The daily escalation budget is spent; stayed with the reason default."
            )
        else:
            model_key = tier.escalation
            reason = (
                "An escalation rule fired; selected the configured reason escalation."
            )

    chosen = config.models[model_key]
    if (
        SENSITIVITY_LEVELS[request.sensitivity]
        > SENSITIVITY_LEVELS[chosen.max_sensitivity]
    ):
        fallback_key = config.router.fallback_model
        if fallback_key is None:
            raise SensitivityRefused(
                "No configured model may receive this request's sensitivity level."
            )
        fallback = config.models[fallback_key]
        if (
            SENSITIVITY_LEVELS[request.sensitivity]
            > SENSITIVITY_LEVELS[fallback.max_sensitivity]
        ):
            raise SensitivityRefused(
                "The configured local fallback cannot receive this sensitivity level."
            )
        chosen = fallback
        model_key = fallback_key
        reason = (
            f"The request exceeds the chosen model's sensitivity ceiling; "
            f"routed to the configured local fallback. {reason}"
        )
    return RouteDecision(
        tier=request.tier,
        model_key=model_key,
        model=chosen,
        reason=reason,
    )
