from __future__ import annotations

from collections.abc import Callable
from typing import Any

from spark.gateway.contracts import (
    Completion,
    ExtractionResponse,
    ModelDescription,
    ToolCall,
    ToolResponse,
)


class MockAdapter:
    def __init__(
        self,
        description: ModelDescription,
        scripted_replies: list[str] | None = None,
        scripted_tool_calls: list[ToolCall] | None = None,
        scripted_extraction: dict[str, Any] | None = None,
        reply_factory: Callable[[list[dict[str, str]]], str] | None = None,
        tool_call_factory: Callable[
            [list[dict[str, str]], list[dict[str, Any]]], list[ToolCall]
        ]
        | None = None,
    ) -> None:
        self.description: ModelDescription = description
        self.scripted_replies: list[str] = scripted_replies or ["Mock response"]
        self.scripted_tool_calls: list[ToolCall] = scripted_tool_calls or []
        self.scripted_extraction: dict[str, Any] = scripted_extraction or {}
        self.reply_factory = reply_factory
        self.tool_call_factory = tool_call_factory
        self.sent: list[dict[str, Any]] = []
        self._reply_index = 0

    def describe(self) -> ModelDescription:
        return self.description

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        self.sent.append({"operation": "complete", "messages": messages})
        text = (
            self.reply_factory(messages)
            if self.reply_factory is not None
            else self.scripted_replies[
                min(self._reply_index, len(self.scripted_replies) - 1)
            ]
        )
        self._reply_index += 1
        content_length = sum(len(message.get("content", "")) for message in messages)
        tokens_in = max(1, content_length // 4)
        return Completion(
            text=text,
            tokens_in=tokens_in,
            tokens_out=max(1, len(text) // 4),
        )

    def call_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> ToolResponse:
        self.sent.append(
            {"operation": "call_tools", "messages": messages, "tools": tools}
        )
        content_length = sum(len(message.get("content", "")) for message in messages)
        tokens_in = max(1, content_length // 4)
        calls = (
            self.tool_call_factory(messages, tools)
            if self.tool_call_factory is not None
            else self.scripted_tool_calls
        )
        return ToolResponse(
            calls=list(calls),
            tokens_in=tokens_in,
            tokens_out=max(1, len(calls)),
        )

    def extract(self, document: str, form: dict[str, Any]) -> ExtractionResponse:
        self.sent.append({"operation": "extract", "document": document, "form": form})
        values = {key: self.scripted_extraction.get(key) for key in form}
        return ExtractionResponse(
            values=values,
            tokens_in=max(1, len(document) // 4),
            tokens_out=max(1, len(values)),
        )
