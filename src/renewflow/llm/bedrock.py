"""Amazon Bedrock adapter using the Converse API with tool use.

Translates the agent's neutral message format into Converse blocks and back. Bedrock requires
alternating user/assistant turns that start with a user turn, and every tool result for one
assistant turn in a single user message; ``to_converse`` guarantees all three.
"""

from __future__ import annotations

import json
from typing import Any

from .base import ModelTurn, ToolCall


def _merge(messages: list[dict[str, Any]], role: str, blocks: list[dict[str, Any]]) -> None:
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"].extend(blocks)
    else:
        messages.append({"role": role, "content": blocks})


def to_converse(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    system: list[dict[str, str]] = []
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system.append({"text": m["content"]})
        elif role == "user":
            _merge(out, "user", [{"text": m["content"] or "(empty)"}])
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"text": m["content"]})
            for call in m.get("tool_calls", []):
                blocks.append(
                    {"toolUse": {"toolUseId": call["id"], "name": call["name"], "input": call["arguments"]}}
                )
            _merge(out, "assistant", blocks or [{"text": "(no content)"}])
        elif role == "tool":
            try:
                parsed = json.loads(m["content"])
            except ValueError:
                parsed = m["content"]
            payload = parsed if isinstance(parsed, dict) else {"result": parsed}
            _merge(
                out,
                "user",
                [{"toolResult": {"toolUseId": m["tool_call_id"], "content": [{"json": payload}]}}],
            )
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"text": "(conversation start)"}]})
    return out, system


def to_tool_config(tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": {"json": t["input_schema"]},
                }
            }
            for t in tools
        ]
    }


class BedrockModel:
    def __init__(self, client: Any, model_id: str, max_tokens: int = 1024, temperature: float = 0.2):
        self.client = client
        self.model_id = model_id
        self.name = f"bedrock:{model_id}"
        self.max_tokens = max_tokens
        self.temperature = temperature

    def respond(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelTurn:
        converse_messages, system = to_converse(messages)
        response = self.client.converse(
            modelId=self.model_id,
            messages=converse_messages,
            system=system,
            toolConfig=to_tool_config(tools),
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": self.temperature},
        )
        blocks = response["output"]["message"]["content"]
        text = "".join(b["text"] for b in blocks if "text" in b).strip() or None
        calls = [
            ToolCall(b["toolUse"]["toolUseId"], b["toolUse"]["name"], b["toolUse"].get("input") or {})
            for b in blocks
            if "toolUse" in b
        ]
        return ModelTurn(text, calls)
