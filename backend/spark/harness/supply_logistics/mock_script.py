from __future__ import annotations

import json
from typing import Any, cast

from spark.gateway.contracts import ToolCall


def _tool_results(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for message in messages:
        try:
            content: Any = json.loads(message["content"])
        except (KeyError, json.JSONDecodeError):
            continue
        if isinstance(content, dict):
            mapping = cast(dict[str, Any], content)
            tool_result = mapping.get("tool_result")
            if isinstance(tool_result, dict):
                found.append(cast(dict[str, Any], tool_result))
    return found


def scripted_tool_calls(
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]],
) -> list[ToolCall]:
    allowed = {tool["name"] for tool in tools}
    results = _tool_results(messages)
    risk_result = next(
        (
            entry["result"]
            for entry in results
            if entry["name"] == "items_within_horizon"
        ),
        None,
    )
    if risk_result is None:
        if "items_within_horizon" in allowed:
            return [
                ToolCall(
                    id="mock-risk-1",
                    name="items_within_horizon",
                    arguments={"location_name": None, "within_days": 60},
                )
            ]
        return []

    items = risk_result.get("items", [])
    if not items:
        return []
    first = items[0]
    item_name = first["item_name"]
    location_name = first["location_name"]
    called = {entry["name"] for entry in results}
    calls: list[ToolCall] = []
    if "item_demand_forecast" in allowed and "item_demand_forecast" not in called:
        calls.append(
            ToolCall(
                id="mock-forecast-1",
                name="item_demand_forecast",
                arguments={
                    "item_name": item_name,
                    "location_name": location_name,
                },
            )
        )
    if "open_purchase_orders" in allowed and "open_purchase_orders" not in called:
        calls.append(
            ToolCall(
                id="mock-orders-1",
                name="open_purchase_orders",
                arguments={"item_name": item_name},
            )
        )
    return calls


def scripted_reply(messages: list[dict[str, str]]) -> str:
    results = _tool_results(messages)
    forecast = next(
        (
            entry["result"]
            for entry in results
            if entry["name"] == "item_demand_forecast"
        ),
        None,
    )
    orders = next(
        (
            entry["result"]
            for entry in results
            if entry["name"] == "open_purchase_orders"
        ),
        None,
    )
    statements: list[dict[str, Any]] = []
    if forecast:
        evidence = forecast["records"]
        statements.append(
            {
                "text": (
                    f"{forecast['item_name']} is projected to reach zero on "
                    f"{forecast['predicted_runout_date']}; the estimate ranges "
                    f"from {forecast['earliest_date']} to {forecast['latest_date']}."
                ),
                "citations": [record["record_id"] for record in evidence],
            }
        )
        if orders and orders.get("records"):
            order = orders["records"][0]
            order_quantity = order["fields"]["quantity"]
            statements.append(
                {
                    "text": (
                        f"The open order is for {order_quantity:g} units, below "
                        f"the projected monthly use of "
                        f"{forecast['projected_monthly_use']:g} units."
                    ),
                    "citations": [
                        *[record["record_id"] for record in evidence],
                        order["record_id"],
                    ],
                }
            )
    return json.dumps({"statements": statements}, separators=(",", ":"))
