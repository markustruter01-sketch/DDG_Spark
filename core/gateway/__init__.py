"""Model gateway: the only place in Omni that talks to an AI model."""
from .contract import Message, ModelAdapter, ModelInfo, ModelReply, ToolCall, ToolSpec
from .mock import MockAdapter
from .router import (
    Decision,
    Gateway,
    GatewayConfig,
    RouteRequest,
    Router,
    Sensitivity,
    SensitivityBlocked,
    SpendLedger,
    Tier,
)

__all__ = [
    "Decision", "Gateway", "GatewayConfig", "Message", "MockAdapter", "ModelAdapter",
    "ModelInfo", "ModelReply", "RouteRequest", "Router", "Sensitivity",
    "SensitivityBlocked", "SpendLedger", "Tier", "ToolCall", "ToolSpec",
]
