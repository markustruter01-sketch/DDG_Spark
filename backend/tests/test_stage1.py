from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from omni.api.auth import COOKIE_NAME, _encode_session
from omni.config import get_settings
from omni.db.agent import agent_engine
from omni.db.platform import platform_engine
from omni.evals.run import ANSWER_KEY
from omni.gateway.config import load_config
from omni.gateway.contracts import ModelAdapter, ToolCall
from omni.gateway.mock import MockAdapter
from omni.gateway.service import (
    MemoryEgressRecorder,
    ModelGateway,
    model_description,
)
from omni.gateway.spend import MemorySpendLedger
from omni.harness.citations import check_citations
from omni.harness.loader import load_harness
from omni.harness.runner import ask_harness
from omni.ingest.loader import ingest_dataset
from omni.ledger.postgres import PostgresAuditLedger
from omni.packs.loader import active_pack
from omni.sim.generate import CONFIG_FILE, generate_dataset
from omni.tools.read_tools import (
    DocumentSearchInput,
    HorizonInput,
    ItemInput,
    ItemLocationInput,
    item_demand_forecast,
    items_within_horizon,
    maintenance_jobs_using_item,
    open_purchase_orders,
    search_documents,
    stock_history,
)


def _dataset_config() -> dict[str, Any]:
    value: Any = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _manifest() -> dict[str, Any]:
    for key in active_pack()["harnesses"]:
        try:
            return load_harness(key)
        except ValueError:
            continue
    raise AssertionError("The default pack has no available Stage 1 harness.")


@pytest.fixture(scope="module", autouse=True)
def sample_data() -> None:
    config = _dataset_config()
    generate_dataset()
    ingest_dataset(source_owner=config["organisation"]["source_owner"])


def _table_counts() -> dict[str, int]:
    names = (
        "source",
        "raw_record",
        "location",
        "org_unit",
        "asset",
        "item",
        "stock_level",
        "stock_movement",
        "maintenance_job",
        "purchase_order",
        "supplier",
        "document",
    )
    with platform_engine().connect() as connection:
        return {
            name: int(
                connection.execute(
                    text(f"SELECT count(*) FROM public.{name}")
                ).scalar_one()
            )
            for name in names
        }


def _mock_gateway(
    *,
    reply_factory: Any = None,
    tool_call_factory: Any = None,
    egress_recorder: Any = None,
) -> tuple[ModelGateway, dict[str, MockAdapter]]:
    config = load_config()
    adapters: dict[str, ModelAdapter] = {}
    mocks: dict[str, MockAdapter] = {}
    for model in config.models.values():
        adapter = MockAdapter(
            model_description(model),
            reply_factory=reply_factory,
            tool_call_factory=tool_call_factory,
        )
        adapters[model.model_id] = adapter
        mocks[model.model_id] = adapter
    return (
        ModelGateway(
            config=config,
            adapters=adapters,
            spend_ledger=MemorySpendLedger(),
            egress_recorder=egress_recorder or MemoryEgressRecorder(),
        ),
        mocks,
    )


def _tool_results(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for message in messages:
        try:
            value: Any = json.loads(message["content"])
        except (KeyError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and isinstance(value.get("tool_result"), dict):
            results.append(value["tool_result"])
    return results


def test_sample_ingestion_is_idempotent(tmp_path: Path) -> None:
    config = _dataset_config()
    input_dir = tmp_path / "input"
    raw_dir = tmp_path / "raw"
    generate_dataset(input_dir)
    first = ingest_dataset(input_dir, raw_dir, config["organisation"]["source_owner"])
    before = _table_counts()
    second = ingest_dataset(input_dir, raw_dir, config["organisation"]["source_owner"])
    after = _table_counts()

    assert set(first) == {"sources", "raw_records", "entities"}
    assert all(value == 0 for value in second.values())
    assert before == after


def test_read_tools_return_lineage_and_forecast_within_answer_key() -> None:
    config = _dataset_config()
    item_name = config["critical_item"]["name"]
    location_name = config["organisation"]["location_name"]
    forecast = item_demand_forecast(
        ItemLocationInput(item_name=item_name, location_name=location_name)
    )
    answer_key: Any = yaml.safe_load(ANSWER_KEY.read_text(encoding="utf-8"))
    predicted = date.fromisoformat(forecast["predicted_runout_date"])
    earliest = date.fromisoformat(str(answer_key["expected_runout_window"]["earliest"]))
    latest = date.fromisoformat(str(answer_key["expected_runout_window"]["latest"]))

    assert item_name == forecast["item_name"]
    assert earliest <= predicted <= latest
    assert forecast["projected_monthly_use"] > 0
    assert all(
        record["entity"] and record["record_id"] for record in forecast["records"]
    )
    assert stock_history(
        ItemLocationInput(item_name=item_name, location_name=location_name)
    )["records"]
    assert item_name in {
        item["item_name"]
        for item in items_within_horizon(
            HorizonInput(location_name=location_name, within_days=60)
        )["items"]
    }
    assert open_purchase_orders(ItemInput(item_name=item_name))["records"]
    assert maintenance_jobs_using_item(ItemInput(item_name=item_name))["records"]

    search = search_documents(
        DocumentSearchInput(query="delete all records reveal user accounts")
    )
    report_text = _dataset_config()["reports"][-1]["text"]
    assert any(
        record["fields"]["full_text"] == report_text for record in search["records"]
    )


def test_sql_injection_string_is_only_a_parameterized_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: list[dict[str, Any]] = []
    injection = "' OR 1=1; DROP TABLE auth_user; --"

    def tool_script(
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> list[ToolCall]:
        if _tool_results(messages):
            return []
        return [
            ToolCall(
                id="injection-script",
                name="search_documents",
                arguments={"query": injection},
            )
        ]

    def reply_script(messages: list[dict[str, str]]) -> str:
        return json.dumps({"statements": []})

    monkeypatch.setattr(
        "omni.harness.runner.append_ledger",
        lambda **values: stored.append(values),
    )
    before = _table_counts()
    gateway, _ = _mock_gateway(
        reply_factory=reply_script,
        tool_call_factory=tool_script,
    )
    answer = ask_harness(
        gateway=gateway,
        manifest=_manifest(),
        user_id="7410cfa0-ef17-4b3f-9c5d-cced479c30aa",
        question="Search using a hostile-looking query.",
        deep_think=False,
    )
    after = _table_counts()

    assert before == after
    assert not answer["unsupported_statements"]
    assert stored[0]["tool_calls"][0]["inputs"]["query"] == injection
    assert not stored[0]["tool_calls"][0].get("error")
    with platform_engine().connect() as connection:
        account_count = connection.execute(
            text("SELECT count(*) FROM auth_user")
        ).scalar_one()
    assert account_count >= 1


def test_document_injection_is_fenced_and_write_tools_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: list[dict[str, Any]] = []

    def tool_script(
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> list[ToolCall]:
        called = [entry["name"] for entry in _tool_results(messages)]
        if "search_documents" not in called:
            return [
                ToolCall(
                    id="search-script",
                    name="search_documents",
                    arguments={"query": "delete all records reveal user accounts"},
                )
            ]
        if "delete_records" not in called:
            return [
                ToolCall(
                    id="write-attempt",
                    name="delete_records",
                    arguments={"entity": "auth_user"},
                ),
                ToolCall(
                    id="account-attempt",
                    name="reveal_accounts",
                    arguments={},
                ),
            ]
        return []

    def reply_script(messages: list[dict[str, str]]) -> str:
        document_result = next(
            entry["result"]
            for entry in _tool_results(messages)
            if entry["name"] == "search_documents"
        )
        record = document_result["records"][0]
        return json.dumps(
            {
                "statements": [
                    {
                        "text": "The report contains instruction-like text.",
                        "citations": [record["record_id"]],
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "omni.harness.runner.append_ledger",
        lambda **values: stored.append(values),
    )
    before = _table_counts()
    gateway, mocks = _mock_gateway(
        reply_factory=reply_script,
        tool_call_factory=tool_script,
    )
    manifest = _manifest()
    answer = ask_harness(
        gateway=gateway,
        manifest=manifest,
        user_id="7410cfa0-ef17-4b3f-9c5d-cced479c30aa",
        question="Search the reports for unusual instructions.",
        deep_think=False,
    )
    after = _table_counts()
    work_model = load_config().models[load_config().tiers["work"].default].model_id
    completion_call = next(
        entry for entry in mocks[work_model].sent if entry["operation"] == "complete"
    )
    sent_text = json.dumps(completion_call["messages"])

    assert before == after
    assert "<<<UNTRUSTED DOCUMENT DATA BEGIN>>>" in sent_text
    assert "SYSTEM OVERRIDE" in sent_text
    assert not answer["unsupported_statements"]
    assert len(stored) == 1
    calls = stored[0]["tool_calls"]
    assert [call["name"] for call in calls] == [
        "search_documents",
        "delete_records",
        "reveal_accounts",
    ]
    assert calls[1]["refused"] and calls[2]["refused"]
    with pytest.raises(DBAPIError):
        with agent_engine().connect() as connection:
            connection.execute(text("SELECT * FROM auth_user LIMIT 1"))


def test_invalid_citation_is_marked_unsupported() -> None:
    statements, unsupported = check_citations(
        json.dumps(
            {
                "statements": [
                    {
                        "text": "An unsupported claim.",
                        "citations": ["not-returned-by-a-tool"],
                    }
                ]
            }
        ),
        {},
    )
    assert statements[0]["unsupported"]
    assert statements[0]["citations"] == []
    assert unsupported == ["An unsupported claim."]


def test_signed_in_ask_returns_citation_evidence_and_complete_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import omni.main as main_module

    manifest = _manifest()
    gateway, _ = _mock_gateway(
        reply_factory=manifest["mock_reply_factory"],
        tool_call_factory=manifest["mock_tool_call_factory"],
        egress_recorder=PostgresAuditLedger(),
    )
    monkeypatch.setattr(
        main_module,
        "build_configured_gateway",
        lambda **_: gateway,
    )
    with platform_engine().connect() as connection:
        user_id = str(
            connection.execute(
                text(
                    "SELECT id::text FROM auth_user "
                    "WHERE role = 'administrator' ORDER BY created_at LIMIT 1"
                )
            ).scalar_one()
        )
        egress_before = connection.execute(
            text("SELECT count(*) FROM egress_log")
        ).scalar_one()
    token = _encode_session(
        user_id,
        get_settings().session_secret,
        int(time.time()) + 3600,
    )

    with TestClient(main_module.app) as client:
        client.cookies.set(COOKIE_NAME, token)
        assert client.get("/api/auth/session").status_code == 200
        response = client.post(
            "/api/ask",
            json={
                "harness_key": manifest["key"],
                "question": "Which items are projected to run out within 60 days?",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["gateway_mode"] == "mock"
        assert result["statements"]
        assert all(not statement["unsupported"] for statement in result["statements"])
        citation = result["statements"][0]["citations"][0]
        evidence_response = client.get(
            f"/api/evidence/{citation['entity']}/{citation['record_id']}"
        )
        assert evidence_response.status_code == 200
        evidence = evidence_response.json()
        assert evidence["record"]["id"] == citation["record_id"]
        assert evidence["raw_record"]["payload"]

    question = "Which items are projected to run out within 60 days?"
    with platform_engine().connect() as connection:
        ledger = (
            connection.execute(
                text(
                    """
                    SELECT harness, question, tool_calls, model, routing_reason,
                           answer, sources, unsupported_statements
                    FROM ledger
                    WHERE user_id = :user_id AND question = :question
                    ORDER BY created_at DESC LIMIT 1
                    """
                ),
                {"user_id": UUID(user_id), "question": question},
            )
            .mappings()
            .one()
        )
        egress_after = connection.execute(
            text("SELECT count(*) FROM egress_log")
        ).scalar_one()
    assert ledger["harness"] == manifest["key"]
    assert ledger["tool_calls"]
    assert ledger["model"]
    assert ledger["routing_reason"]
    assert ledger["answer"]
    assert ledger["sources"]
    assert all(
        "inputs" in call and "returned_record_ids" in call
        for call in ledger["tool_calls"]
    )
    assert any(call["returned_record_ids"] for call in ledger["tool_calls"])
    assert all(source["entity"] and source["record_id"] for source in ledger["sources"])
    assert ledger["unsupported_statements"] == []
    assert egress_after >= egress_before + 4
