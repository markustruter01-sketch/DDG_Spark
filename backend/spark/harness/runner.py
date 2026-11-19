from __future__ import annotations

import json
from typing import Any, cast

from pydantic import ValidationError

from spark.gateway.router import RouteRequest
from spark.gateway.service import ModelGateway
from spark.harness.citations import answer_as_text, check_citations
from spark.ledger.postgres import append_ledger
from spark.tools.registry import ReadTool, declared_tools


def _model_safe(value: Any) -> Any:
    if isinstance(value, list):
        return [_model_safe(item) for item in cast(list[Any], value)]
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        safe = {key: _model_safe(item) for key, item in mapping.items()}
        fields = safe.get("fields")
        if isinstance(fields, dict):
            field_values = cast(dict[str, Any], fields)
        else:
            field_values = {}
        if isinstance(field_values.get("full_text"), str):
            field_values["full_text"] = (
                "<<<UNTRUSTED DOCUMENT DATA BEGIN>>>\n"
                + field_values["full_text"]
                + "\n<<<UNTRUSTED DOCUMENT DATA END>>>"
            )
        return safe
    return value


def _collect_records(value: Any, output: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, list):
        for item in cast(list[Any], value):
            _collect_records(item, output)
    elif isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        if isinstance(mapping.get("record_id"), str) and isinstance(
            mapping.get("entity"), str
        ):
            output[mapping["record_id"]] = {
                "entity": mapping["entity"],
                "record_id": mapping["record_id"],
            }
        for item in mapping.values():
            _collect_records(item, output)


def _tool_result_ids(value: Any) -> list[str]:
    found: dict[str, dict[str, Any]] = {}
    _collect_records(value, found)
    return sorted(found)


def _tool_error(call_name: str, error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "The tool arguments did not match its required input."
    return f"The declared read tool {call_name} could not complete."


def ask_harness(
    *,
    gateway: ModelGateway,
    manifest: dict[str, Any],
    user_id: str,
    question: str,
    deep_think: bool,
) -> dict[str, Any]:
    declared: list[ReadTool] = declared_tools(manifest["tools"])
    tools_by_name = {tool.name: tool for tool in declared}
    tool_schemas = [tool.schema() for tool in declared]
    maximum_rounds = min(5, max(1, int(manifest.get("maximum_tool_rounds", 3))))
    tier = "reason" if deep_think else "work"
    request = RouteRequest(
        tier=tier,
        sensitivity="internal",
        deep_think=deep_think,
        harness_count=1,
    )
    messages = [
        {"role": "system", "content": manifest["instructions_text"]},
        {
            "role": "user",
            "content": (
                question
                + "\nReturn a JSON object with a statements array. Each statement "
                "must contain text and citations, an array of exact record ids."
            ),
        },
    ]
    tool_log: list[dict[str, Any]] = []
    returned_records: dict[str, dict[str, Any]] = {}

    for _ in range(maximum_rounds):
        _, response, _ = gateway.run_tools(request, messages, tool_schemas)
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "tool_calls": [
                            {"name": call.name, "arguments": call.arguments}
                            for call in response.calls
                        ]
                    },
                    separators=(",", ":"),
                ),
            }
        )
        if not response.calls:
            break

        for call in response.calls:
            tool = tools_by_name.get(call.name)
            entry: dict[str, Any] = {
                "name": call.name,
                "inputs": call.arguments,
                "returned_record_ids": [],
            }
            if tool is None:
                entry["refused"] = True
                entry["reason"] = "The tool is not declared for this harness."
                result: dict[str, Any] = {"refused": entry["reason"]}
            else:
                try:
                    result = tool.execute(call.arguments)
                    _collect_records(result, returned_records)
                    entry["returned_record_ids"] = _tool_result_ids(result)
                except Exception as error:
                    entry["error"] = _tool_error(call.name, error)
                    result = {"error": entry["error"]}
            tool_log.append(entry)
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "tool_result": {
                                "name": call.name,
                                "result": _model_safe(result),
                            }
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )

    gateway_result = gateway.run(request, messages)
    statements, unsupported = check_citations(
        gateway_result.completion.text,
        returned_records,
    )
    answer_text = answer_as_text(statements)
    sources = sorted(
        returned_records.values(),
        key=lambda item: (item["entity"], item["record_id"]),
    )
    append_ledger(
        user_id=user_id,
        harness=manifest["key"],
        question=question,
        tool_calls=tool_log,
        model=gateway_result.decision.model.model_id,
        routing_reason=gateway_result.decision.reason,
        answer=answer_text,
        sources=sources,
        unsupported_statements=unsupported,
    )
    return {
        "harness": manifest["key"],
        "statements": statements,
        "unsupported_statements": unsupported,
        "model": gateway_result.decision.model.model_id,
        "routing_reason": gateway_result.decision.reason,
        "gateway_mode": gateway.health()["mode"],
    }
