"""The adapter contract.

Anything that implements ModelAdapter can run Omni. Nothing outside
core/gateway may import a vendor SDK or name a specific model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Message:
    role: str  # "user" | "assistant" | "tool"
    content: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the arguments


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ModelInfo:
    name: str
    provider: str
    context_tokens: int
    supports_tools: bool
    local: bool  # True when the model runs on the customer's own hardware


@runtime_checkable
class ModelAdapter(Protocol):
    """Four functions. Implement them and the model slots in."""

    def describe(self) -> ModelInfo: ...

    def complete(
        self, messages: list[Message], system: str | None = None, max_tokens: int = 2048
    ) -> ModelReply: ...

    def call_tools(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> ModelReply: ...

    def extract(
        self, document: str, schema: dict[str, Any], instructions: str
    ) -> dict[str, Any]: ...
