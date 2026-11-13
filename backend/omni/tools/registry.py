from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

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


@dataclass(frozen=True)
class ReadTool:
    name: str
    input_model: type[BaseModel]
    handler: Callable[[Any], dict[str, Any]]
    description: str

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        validated = self.input_model.model_validate(arguments)
        return self.handler(validated)


TOOLS: dict[str, ReadTool] = {
    "item_history": ReadTool(
        "item_history",
        ItemLocationInput,
        stock_history,
        "Read recorded quantities and movements for one item at one location.",
    ),
    "item_demand_forecast": ReadTool(
        "item_demand_forecast",
        ItemLocationInput,
        item_demand_forecast,
        (
            "Project when the recorded quantity reaches zero using recent "
            "movement history."
        ),
    ),
    "items_within_horizon": ReadTool(
        "items_within_horizon",
        HorizonInput,
        items_within_horizon,
        (
            "Rank items projected to reach zero within the requested days and list "
            "items that could not be forecast with a plain reason."
        ),
    ),
    "open_purchase_orders": ReadTool(
        "open_purchase_orders",
        ItemInput,
        open_purchase_orders,
        "Read open orders recorded for one item.",
    ),
    "maintenance_jobs_using_item": ReadTool(
        "maintenance_jobs_using_item",
        ItemInput,
        maintenance_jobs_using_item,
        "Read recorded work connected to movements of one item.",
    ),
    "search_documents": ReadTool(
        "search_documents",
        DocumentSearchInput,
        search_documents,
        "Search document text using a fixed, parameterized full-text query.",
    ),
}


def declared_tools(names: list[str]) -> list[ReadTool]:
    unknown = set(names) - TOOLS.keys()
    if unknown:
        raise ValueError(f"Harness declares unavailable read tools: {sorted(unknown)}")
    return [TOOLS[name] for name in names]
