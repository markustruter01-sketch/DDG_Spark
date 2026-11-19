from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelDescription:
    name: str
    provider: str
    context_size: int
    supports_tools: bool
    runs_locally: bool


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResponse:
    calls: list[ToolCall]
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class ExtractionResponse:
    values: dict[str, Any]
    tokens_in: int
    tokens_out: int


class ModelAdapter(Protocol):
    def describe(self) -> ModelDescription: ...

    def complete(self, messages: list[dict[str, str]]) -> Completion: ...

    def call_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> ToolResponse: ...

    def extract(self, document: str, form: dict[str, Any]) -> ExtractionResponse: ...
