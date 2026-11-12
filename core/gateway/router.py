"""Routing: which model answers this request, and why.

Harnesses ask for a tier, never a model. The router applies, in order:
  1. the tier's default model
  2. escalation rules (Reason tier only), limited by a daily budget
  3. the sensitivity ceiling of the chosen model
Every decision carries a plain-English reason for the ledger and the dashboard.
"""
from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Callable

from .contract import Message, ModelAdapter, ModelReply, ToolSpec


class Tier(str, Enum):
    REASON = "reason"  # orchestration, cross-harness answers, the challenger
    WORK = "work"      # harness agents, briefs, mapping proposals
    BULK = "bulk"      # reading and extracting from many documents


class Sensitivity(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    RESTRICTED = 2


class SensitivityBlocked(Exception):
    """No configured model is allowed to see data this sensitive."""


@dataclass(frozen=True)
class ModelEntry:
    key: str
    model_id: str
    provider: str
    max_sensitivity: Sensitivity
    usd_per_mtok_in: float
    usd_per_mtok_out: float


@dataclass(frozen=True)
class GatewayConfig:
    tier_default: dict[Tier, str]
    reason_escalation: str | None
    local_fallback: str | None
    escalate_min_harnesses: int
    escalate_citation_failures: int
    daily_escalation_budget_usd: float
    models: dict[str, ModelEntry]

    @classmethod
    def load(cls, path: str | Path) -> "GatewayConfig":
        return cls.from_dict(tomllib.loads(Path(path).read_text()))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GatewayConfig":
        models = {
            key: ModelEntry(
                key=key,
                model_id=m["model_id"],
                provider=m["provider"],
                max_sensitivity=Sensitivity[m.get("max_sensitivity", "INTERNAL").upper()],
                usd_per_mtok_in=float(m.get("usd_per_mtok_in", 0.0)),
                usd_per_mtok_out=float(m.get("usd_per_mtok_out", 0.0)),
            )
            for key, m in raw["models"].items()
        }
        tiers, esc = raw["tiers"], raw.get("escalation", {})
        config = cls(
            tier_default={Tier(t): tiers[t] for t in ("reason", "work", "bulk")},
            reason_escalation=tiers.get("reason_escalation"),
            local_fallback=tiers.get("local_fallback"),
            escalate_min_harnesses=int(esc.get("min_harnesses", 3)),
            escalate_citation_failures=int(esc.get("citation_failures", 2)),
            daily_escalation_budget_usd=float(esc.get("daily_budget_usd", 0.0)),
            models=models,
        )
        named = [*config.tier_default.values(), config.reason_escalation, config.local_fallback]
        missing = sorted({k for k in named if k and k not in models})
        if missing:
            raise ValueError(f"tiers refer to models that are not defined: {missing}")
        return config


@dataclass(frozen=True)
class RouteRequest:
    tier: Tier
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    deep_think: bool = False           # the user's manual switch
    harness_count: int = 1             # how many harnesses the question spans
    challenger_disagrees: bool = False
    citation_failures: int = 0


@dataclass(frozen=True)
class Decision:
    model_key: str
    model_id: str
    reason: str
    escalated: bool = False
    fell_back: bool = False


class SpendLedger:
    """Running cost per model per day. In-memory here; Stage 4 persists it."""

    def __init__(self, today: Callable[[], dt.date] = dt.date.today):
        self._today = today
        self._spend: dict[tuple[dt.date, str], float] = {}

    def record(self, entry: ModelEntry, input_tokens: int, output_tokens: int) -> float:
        cost = (input_tokens * entry.usd_per_mtok_in + output_tokens * entry.usd_per_mtok_out) / 1_000_000
        key = (self._today(), entry.key)
        self._spend[key] = self._spend.get(key, 0.0) + cost
        return cost

    def spent_today(self, model_key: str) -> float:
        return self._spend.get((self._today(), model_key), 0.0)


class Router:
    def __init__(self, config: GatewayConfig, ledger: SpendLedger | None = None):
        self.config = config
        self.ledger = ledger or SpendLedger()

    def _escalation_trigger(self, req: RouteRequest) -> str | None:
        c = self.config
        if req.deep_think:
            return "deep think was switched on for this question"
        if req.harness_count >= c.escalate_min_harnesses:
            return f"the question spans {req.harness_count} harnesses"
        if req.challenger_disagrees:
            return "the challenger disagreed with the first answer"
        if req.citation_failures >= c.escalate_citation_failures:
            return f"the citation check failed {req.citation_failures} times"
        return None

    def choose(self, req: RouteRequest) -> Decision:
        c = self.config
        key = c.tier_default[req.tier]
        reason = f"default model for the {req.tier.value} tier"
        escalated = fell_back = False

        trigger = self._escalation_trigger(req) if req.tier is Tier.REASON else None
        if trigger and c.reason_escalation:
            if self.ledger.spent_today(c.reason_escalation) < c.daily_escalation_budget_usd:
                key, escalated, reason = c.reason_escalation, True, f"escalated because {trigger}"
            else:
                fell_back = True
                reason = f"would have escalated because {trigger}, but today's escalation budget is spent"

        if req.sensitivity > c.models[key].max_sensitivity:
            local = c.local_fallback
            if not local or req.sensitivity > c.models[local].max_sensitivity:
                raise SensitivityBlocked(
                    f"no configured model may receive {req.sensitivity.name} data"
                )
            key, escalated, fell_back = local, False, True
            reason = f"{req.sensitivity.name} data may not leave; routed to the local model"

        return Decision(key, c.models[key].model_id, reason, escalated, fell_back)


@dataclass
class GatewayResult:
    reply: ModelReply
    decision: Decision
    cost_usd: float


@dataclass
class Gateway:
    """The single entry point for every model call in Omni."""

    router: Router
    adapters: dict[str, ModelAdapter]
    on_call: Callable[[dict[str, Any]], None] | None = None  # feeds the egress log

    def run(
        self,
        req: RouteRequest,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        system: str | None = None,
    ) -> GatewayResult:
        decision = self.router.choose(req)
        adapter = self.adapters[decision.model_key]
        reply = (
            adapter.call_tools(messages, tools, system=system)
            if tools
            else adapter.complete(messages, system=system)
        )
        entry = self.router.config.models[decision.model_key]
        cost = self.router.ledger.record(entry, reply.input_tokens, reply.output_tokens)
        if self.on_call:
            self.on_call(
                {
                    "model_key": decision.model_key,
                    "model_id": decision.model_id,
                    "local": adapter.describe().local,
                    "reason": decision.reason,
                    "sensitivity": req.sensitivity.name,
                    "sent": [m.content for m in messages],
                    "cost_usd": cost,
                }
            )
        return GatewayResult(reply, decision, cost)
