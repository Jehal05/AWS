"""The one interface every messaging channel implements, local or AWS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..store import Customer

# Hard length limits per channel; the guardrails enforce them before anything is sent.
MAX_LENGTH = {"whatsapp": 1000, "email": 5000, "sms": 480}


@dataclass
class OutboundMessage:
    customer: Customer
    channel: str
    body: str
    subject: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
    delivered: bool = False


class Channel(Protocol):
    name: str

    def send(self, message: OutboundMessage) -> SendResult: ...
