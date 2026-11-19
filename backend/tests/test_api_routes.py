from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from spark.api.auth import require_session
from spark.api.routes import router
from spark.gateway.config import load_config
from spark.gateway.service import build_mock_gateway
from spark.packs.loader import PACK_DIR, active_pack_name, load_pack, public_pack


def api_test_app(authenticated: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.gateway = build_mock_gateway()
    if authenticated:
        user: dict[str, Any] = {
            "user_id": "7410cfa0-ef17-4b3f-9c5d-cced479c30aa",
            "email": "test@spark.local",
            "role": "administrator",
            "clearance": "restricted",
        }
        app.dependency_overrides[require_session] = lambda: user
    return app


def test_models_route_requires_a_session() -> None:
    with TestClient(api_test_app(authenticated=False)) as client:
        response = client.get("/api/models")
    assert response.status_code == 401


def test_models_route_reports_configured_tiers() -> None:
    config = load_config()
    with TestClient(api_test_app(authenticated=True)) as client:
        response = client.get("/api/models")

    assert response.status_code == 200
    tiers = response.json()["tiers"]
    for tier_name, tier in config.tiers.items():
        assert tiers[tier_name]["model"] == config.models[tier.default].model_id
        if tier.escalation:
            assert (
                tiers[tier_name]["escalation_model"]
                == config.models[tier.escalation].model_id
            )
    assert response.json()["daily_escalation_budget_usd"] == (
        config.router.daily_escalation_budget_usd
    )
    spend = response.json()["daily_spend_usd"]
    assert set(spend) == {model.model_id for model in config.models.values()}
    assert all(Decimal(value) == 0 for value in spend.values())


def test_pack_route_returns_the_loaded_pack_for_a_session() -> None:
    with TestClient(api_test_app(authenticated=True)) as client:
        response = client.get("/api/pack")

    assert response.status_code == 200
    pack = response.json()
    expected = public_pack()
    assert pack == expected
    assert len(pack["harnesses"]) == 6


def test_pack_route_uses_the_environment_selected_pack(
    monkeypatch,
) -> None:
    available = {
        path.stem for path in PACK_DIR.glob("*.yaml") if path.name != "pack-config.yaml"
    }
    alternate = next(name for name in available if name != active_pack_name())
    monkeypatch.setenv("SPARK_PACK", alternate)
    load_pack.cache_clear()
    with TestClient(api_test_app(authenticated=True)) as client:
        response = client.get("/api/pack")

    pack = response.json()
    assert response.status_code == 200
    assert pack == public_pack()
    assert len(pack["harnesses"]) == 6
    assert len(pack["entities"]) == 5
    load_pack.cache_clear()
