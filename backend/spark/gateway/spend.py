from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Protocol


class SpendLedger(Protocol):
    def total_for_model(self, model_id: str, day: date) -> Decimal: ...

    def record(self, model_id: str, day: date, cost_usd: Decimal) -> None: ...


class MemorySpendLedger:
    def __init__(self) -> None:
        self._spend: dict[tuple[str, date], Decimal] = defaultdict(Decimal)

    def total_for_model(self, model_id: str, day: date) -> Decimal:
        return self._spend[(model_id, day)]

    def record(self, model_id: str, day: date, cost_usd: Decimal) -> None:
        self._spend[(model_id, day)] += cost_usd


def call_cost(
    tokens_in: int,
    tokens_out: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> Decimal:
    input_cost = Decimal(tokens_in) * Decimal(str(input_price_per_million))
    output_cost = Decimal(tokens_out) * Decimal(str(output_price_per_million))
    return (input_cost + output_cost) / Decimal(1_000_000)
