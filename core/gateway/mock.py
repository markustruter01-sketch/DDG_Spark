"""A scripted fake model. Every automated test runs on this and costs nothing."""
from __future__ import annotations

from typing import Any

from .contract import Message, ModelInfo, ModelReply, ToolSpec


class MockAdapter:
    def __init__(self, name: str = "mock", local: bool = False, script: list[ModelReply] | None = None):
        self._name = name
        self._local = local
        self._script = list(script or [])
        self.calls: list[dict[str, Any]] = []

    def describe(self) -> ModelInfo:
        return ModelInfo(self._name, "mock", 200_000, True, self._local)

    def _next(self, kind: str, messages: list[Message]) -> ModelReply:
        self.calls.append({"kind": kind, "messages": messages})
        if self._script:
            return self._script.pop(0)
        return ModelReply(text=f"[{self._name}] ok", input_tokens=10, output_tokens=5)

    def complete(self, messages, system=None, max_tokens=2048) -> ModelReply:
        return self._next("complete", messages)

    def call_tools(self, messages, tools: list[ToolSpec], system=None, max_tokens=2048) -> ModelReply:
        return self._next("call_tools", messages)

    def extract(self, document: str, schema: dict[str, Any], instructions: str) -> dict[str, Any]:
        self.calls.append({"kind": "extract", "document": document})
        return {key: None for key in schema.get("properties", {})}
