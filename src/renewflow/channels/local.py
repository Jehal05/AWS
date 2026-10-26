"""Local channel: nothing leaves the process. The dashboard's device simulator shows it."""

from __future__ import annotations

import uuid

from .base import OutboundMessage, SendResult


class LocalChannel:
    def __init__(self, name: str):
        self.name = name

    def send(self, message: OutboundMessage) -> SendResult:
        customer = message.customer
        address = customer.email if self.name == "email" else customer.phone
        if not address:
            return SendResult(ok=False, error=f"no {self.name} address on file")
        return SendResult(
            ok=True, provider_message_id=f"local-{self.name}-{uuid.uuid4().hex[:10]}", delivered=True
        )
