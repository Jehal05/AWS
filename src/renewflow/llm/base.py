"""Model-agnostic chat interface. The agent loop only ever sees this."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelTurn:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class ChatModel(Protocol):
    name: str

    def respond(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelTurn:
        """Return either tool calls to execute or a final text (no tool calls)."""
        ...
