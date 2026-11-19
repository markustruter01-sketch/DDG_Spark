from __future__ import annotations

import os
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
class ProviderConfig:
    name: str
    kind: str
    key_env: str | None = None
    base_url: str | None = None
    free_tier: bool = False


PROVIDER_KINDS = {"anthropic", "openai-compatible", "local"}


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
    profile: str


@dataclass(frozen=True)
class GatewayConfig:
    models: dict[str, ModelConfig]
    tiers: dict[str, TierConfig]
    router: RouterConfig
    providers: dict[str, ProviderConfig]
    profile: str


def load_config(path: Path = CONFIG_FILE) -> GatewayConfig:
    raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    providers = {
        key: ProviderConfig(name=key, **values)
        for key, values in raw["providers"].items()
    }
    models = {
        key: ModelConfig(key=key, **values) for key, values in raw["models"].items()
    }
    profiles = {
        name: {key: TierConfig(**values) for key, values in tiers.items()}
        for name, tiers in raw["profiles"].items()
    }
    router = RouterConfig(**raw["router"])
    for key, provider in providers.items():
        if provider.kind not in PROVIDER_KINDS:
            raise ValueError(f"Provider {key} has an unknown kind.")
        if provider.kind == "openai-compatible" and not provider.base_url:
            raise ValueError(f"Provider {key} needs a base_url.")
        if provider.kind != "local" and not provider.key_env:
            raise ValueError(f"Provider {key} needs a key_env.")
    for key, model in models.items():
        if model.provider not in providers:
            raise ValueError(f"Model entry {key} refers to an undefined provider.")
        if model.max_sensitivity not in SENSITIVITY_LEVELS:
            raise ValueError(f"Model entry {key} has an invalid sensitivity ceiling.")
        if model.price_input_per_million < 0 or model.price_output_per_million < 0:
            raise ValueError(f"Model entry {key} has a negative price.")
    for profile_name, tiers in profiles.items():
        for tier_name, tier in tiers.items():
            where = f"Tier {profile_name}.{tier_name}"
            if tier.default not in models:
                raise ValueError(f"{where} refers to an undefined default model.")
            if tier.escalation and tier.escalation not in models:
                raise ValueError(f"{where} refers to an undefined escalation model.")
    if router.fallback_model and router.fallback_model not in models:
        raise ValueError("The fallback setting refers to an undefined model.")
    profile = os.getenv("SPARK_MODEL_PROFILE") or router.profile
    if profile not in profiles:
        raise ValueError(f"Model profile {profile!r} is not defined.")
    return GatewayConfig(
        models=models,
        tiers=profiles[profile],
        router=router,
        providers=providers,
        profile=profile,
    )
