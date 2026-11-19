from __future__ import annotations

import pytest

from spark.gateway.config import load_config
from spark.gateway.mock import MockAdapter
from spark.gateway.providers import OpenAICompatibleAdapter, configured_adapters
from spark.gateway.service import build_configured_gateway

KEY_NAMES = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "GOOGLE_GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
)


@pytest.fixture(autouse=True)
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*KEY_NAMES, "SPARK_MODEL_PROFILE"):
        monkeypatch.delenv(name, raising=False)


def test_free_profile_is_the_default() -> None:
    config = load_config()
    assert config.profile == "free"
    for tier in config.tiers.values():
        provider = config.providers[config.models[tier.default].provider]
        assert provider.free_tier


def test_profile_can_be_switched_by_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_MODEL_PROFILE", "claude")
    config = load_config()
    assert config.profile == "claude"
    assert config.models[config.tiers["reason"].default].provider == "anthropic"


def test_unknown_profile_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_MODEL_PROFILE", "missing")
    with pytest.raises(ValueError, match="not defined"):
        load_config()


def test_without_keys_every_model_runs_on_the_mock() -> None:
    adapters = configured_adapters(load_config())
    assert all(isinstance(a, MockAdapter) for a in adapters.values())


def test_a_key_connects_only_its_own_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    config = load_config()
    adapters = configured_adapters(config)
    for model in config.models.values():
        adapter = adapters[model.model_id]
        if model.provider == "groq":
            assert isinstance(adapter, OpenAICompatibleAdapter)
        else:
            assert isinstance(adapter, MockAdapter)


def test_model_status_reports_providers_by_key_name_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    status = build_configured_gateway().model_status()
    assert status["profile"] == "free"
    providers = {p["name"]: p for p in status["providers"]}
    assert providers["groq"]["connected"] is True
    assert providers["groq"]["key_name"] == "GROQ_API_KEY"
    assert providers["gemini"]["connected"] is False
    assert "test-key-not-real" not in repr(status)
    assert status["tiers"]["work"]["live"] is True
    assert status["tiers"]["reason"]["live"] is False
