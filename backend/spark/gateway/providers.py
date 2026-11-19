from __future__ import annotations

import json
import os
from typing import Any, cast

from spark.gateway.config import GatewayConfig, ModelConfig
from spark.gateway.contracts import (
    Completion,
    ExtractionResponse,
    ModelAdapter,
    ModelDescription,
    ToolCall,
    ToolResponse,
)


def _description(model: ModelConfig) -> ModelDescription:
    return ModelDescription(
        name=model.model_id,
        provider=model.provider,
        context_size=model.context_size,
        supports_tools=model.supports_tools,
        runs_locally=model.runs_locally,
    )


def _messages(
    messages: list[dict[str, str]],
) -> tuple[str | None, list[dict[str, str]]]:
    systems = [
        message["content"] for message in messages if message["role"] == "system"
    ]
    conversation = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message["role"] != "system"
    ]
    return ("\n\n".join(systems) or None, conversation)


def _token_count(usage: Any, key: str) -> int:
    count = getattr(usage, key, 0)
    return int(count) if isinstance(count, int) else 0


class AnthropicAdapter:
    def __init__(self, model: ModelConfig, api_key: str) -> None:
        import anthropic

        self.model = model
        self.client: Any = anthropic.Anthropic(api_key=api_key)

    def describe(self) -> ModelDescription:
        return _description(self.model)

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        system, conversation = _messages(messages)
        response = self.client.messages.create(
            model=self.model.model_id,
            max_tokens=4096,
            system=system or anthropic_default_system(),
            messages=conversation,
        )
        content = "\n".join(
            str(block.text)
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return Completion(
            text=content,
            tokens_in=_token_count(response.usage, "input_tokens"),
            tokens_out=_token_count(response.usage, "output_tokens"),
        )

    def call_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> ToolResponse:
        system, conversation = _messages(messages)
        provider_tools = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in tools
        ]
        response = self.client.messages.create(
            model=self.model.model_id,
            max_tokens=4096,
            system=system or anthropic_default_system(),
            messages=conversation,
            tools=provider_tools,
        )
        calls = [
            ToolCall(
                id=str(block.id),
                name=str(block.name),
                arguments=dict(block.input),
            )
            for block in response.content
            if getattr(block, "type", None) == "tool_use"
        ]
        return ToolResponse(
            calls=calls,
            tokens_in=_token_count(response.usage, "input_tokens"),
            tokens_out=_token_count(response.usage, "output_tokens"),
        )

    def extract(self, document: str, form: dict[str, Any]) -> ExtractionResponse:
        schema = (
            form
            if "properties" in form
            else {
                "type": "object",
                "properties": form,
                "required": list(form),
                "additionalProperties": False,
            }
        )
        response = self.client.messages.create(
            model=self.model.model_id,
            max_tokens=4096,
            system="Extract only the requested fields from the supplied document.",
            messages=[{"role": "user", "content": document}],
            tools=[
                {
                    "name": "extract_fields",
                    "description": "Return values for the fixed extraction form.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "extract_fields"},
        )
        values: dict[str, Any] = {}
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                values = dict(block.input)
                break
        return ExtractionResponse(
            values=values,
            tokens_in=_token_count(response.usage, "input_tokens"),
            tokens_out=_token_count(response.usage, "output_tokens"),
        )


class OpenAICompatibleAdapter:
    def __init__(self, model: ModelConfig, api_key: str, base_url: str) -> None:
        from openai import OpenAI

        self.model = model
        self.client: Any = OpenAI(api_key=api_key, base_url=base_url)

    def describe(self) -> ModelDescription:
        return _description(self.model)

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        response = self.client.chat.completions.create(
            model=self.model.model_id,
            messages=messages,
        )
        usage = response.usage
        text_value = response.choices[0].message.content or ""
        return Completion(
            text=text_value,
            tokens_in=_token_count(usage, "prompt_tokens"),
            tokens_out=_token_count(usage, "completion_tokens"),
        )

    def call_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> ToolResponse:
        provider_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]
        response = self.client.chat.completions.create(
            model=self.model.model_id,
            messages=messages,
            tools=provider_tools,
            tool_choice="auto",
        )
        raw_calls = cast(
            list[Any],
            response.choices[0].message.tool_calls or [],
        )
        calls: list[ToolCall] = []
        for call in raw_calls:
            function: Any = call.function
            calls.append(
                ToolCall(
                    id=str(call.id),
                    name=str(function.name),
                    arguments=json.loads(str(function.arguments)),
                )
            )
        return ToolResponse(
            calls=calls,
            tokens_in=_token_count(response.usage, "prompt_tokens"),
            tokens_out=_token_count(response.usage, "completion_tokens"),
        )

    def extract(self, document: str, form: dict[str, Any]) -> ExtractionResponse:
        response = self.client.chat.completions.create(
            model=self.model.model_id,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract only the requested fields. Return one JSON object "
                        "matching this schema: "
                        + json.dumps(form, separators=(",", ":"))
                    ),
                },
                {"role": "user", "content": document},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        values = json.loads(content)
        return ExtractionResponse(
            values=values,
            tokens_in=_token_count(response.usage, "prompt_tokens"),
            tokens_out=_token_count(response.usage, "completion_tokens"),
        )


def anthropic_default_system() -> str:
    return "Answer the user's request using the provided context."


def configured_adapters(
    config: GatewayConfig,
    *,
    reply_factory: Any = None,
    tool_call_factory: Any = None,
) -> dict[str, ModelAdapter]:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_url = os.getenv("OPENAI_BASE_URL")
    adapters: dict[str, ModelAdapter] = {}
    for model in config.models.values():
        if model.provider == "anthropic" and anthropic_key:
            adapter: ModelAdapter = AnthropicAdapter(model, anthropic_key)
        elif model.provider == "openai-compatible" and openai_key and openai_url:
            adapter = OpenAICompatibleAdapter(model, openai_key, openai_url)
        else:
            from spark.gateway.mock import MockAdapter

            adapter = MockAdapter(
                _description(model),
                reply_factory=reply_factory,
                tool_call_factory=tool_call_factory,
            )
        adapters[model.model_id] = adapter
    return adapters
