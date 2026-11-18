from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILE = Path(__file__).with_name("config.toml")
SENSITIVITY_LEVELS = {"public": 0, "internal": 1, "restricted": 2}


@dataclass(frozen=True)
class ModelConfig:
    key: str
    provider: str
    model_id: str
    max_sensitivity: str
    price_input_per_million: float
    price_output_per_million: float
    context_size: int
    supports_tools: bool
    runs_locally: bool


@dataclass(frozen=True)
class TierConfig:
    default: str
    escalation: str | None = None


@dataclass(frozen=True)
class RouterConfig:
    minimum_harnesses: int
    citation_failures: int
    daily_escalation_budget_usd: float
    fallback_model: str | None


@dataclass(frozen=True)
class GatewayConfig:
    models: dict[str, ModelConfig]
    tiers: dict[str, TierConfig]
    router: RouterConfig


def load_config(path: Path = CONFIG_FILE) -> GatewayConfig:
    raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    models = {
        key: ModelConfig(key=key, **values) for key, values in raw["models"].items()
    }
    tiers = {key: TierConfig(**values) for key, values in raw["tiers"].items()}
    router = RouterConfig(**raw["router"])
    for key, model in models.items():
        if model.max_sensitivity not in SENSITIVITY_LEVELS:
            raise ValueError(f"Model entry {key} has an invalid sensitivity ceiling.")
        if model.price_input_per_million < 0 or model.price_output_per_million < 0:
            raise ValueError(f"Model entry {key} has a negative price.")
    for tier_name, tier in tiers.items():
        if tier.default not in models:
            raise ValueError(f"Tier {tier_name} refers to an undefined default model.")
        if tier.escalation and tier.escalation not in models:
            raise ValueError(
                f"Tier {tier_name} refers to an undefined escalation model."
            )
    if router.fallback_model and router.fallback_model not in models:
        raise ValueError("The fallback setting refers to an undefined model.")
    return GatewayConfig(models=models, tiers=tiers, router=router)
