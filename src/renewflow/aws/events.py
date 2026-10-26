"""Turns provider events (WhatsApp messages and receipts, SES delivery events) into RenewFlow
actions. Pure logic with no HTTP, so it is tested directly with sample payloads.

Every handler is idempotent: SNS delivers at least once, so the same event can arrive twice.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from ..clock import iso
from ..service import RenewFlow

log = logging.getLogger("renewflow.aws")

WHATSAPP_NON_TEXT = "[The customer sent a message that is not text (an attachment, location or sticker).]"


def _text_of(message: dict[str, Any]) -> str:
    kind = message.get("type")
    if kind == "text":
        return message.get("text", {}).get("body", "").strip()
    if kind == "button":
        return message.get("button", {}).get("text", "").strip()
    if kind == "interactive":
        reply = message.get("interactive", {})
        picked = reply.get("button_reply") or reply.get("list_reply") or {}
        return (picked.get("title") or "").strip()
    return ""


class AwsEventProcessor:
    def __init__(self, svc: RenewFlow):
        self.svc = svc
        self.store = svc.store

    # ------------------------------------------------------------------ entry point
    def process(self, event: dict[str, Any]) -> dict[str, int]:
        """Handle one SNS message body (already parsed). Returns counts for logging and tests."""
        counts = {"inbound": 0, "receipts": 0, "ignored": 0}
        if "whatsAppWebhookEntry" in event:
            entry = event["whatsAppWebhookEntry"]
            entry = json.loads(entry) if isinstance(entry, str) else entry
            self._whatsapp(entry, counts)
        elif "eventType" in event or "notificationType" in event:
            self._ses(event, counts)
        else:
            counts["ignored"] += 1
        return counts

    # ------------------------------------------------------------------ WhatsApp
    def _whatsapp(self, entry: dict[str, Any], counts: dict[str, int]) -> None:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status in value.get("statuses", []):
                counts["receipts" if self._whatsapp_status(status) else "ignored"] += 1
            for message in value.get("messages", []):
                counts["inbound" if self._whatsapp_inbound(message) else "ignored"] += 1

    def _whatsapp_status(self, status: dict[str, Any]) -> bool:
        stored = self.store.message_by_provider_id(status.get("id", ""), "out")
        if stored is None:
            return False  # a receipt for something we did not send, or sent before this database
        kind = status.get("status")
        ts = _epoch_iso(status.get("timestamp"))
        if kind == "delivered" and not self.store.has_event(stored["id"], "delivered"):
            self._event(stored, "delivered", ts)
        elif kind == "read":
            if not self.store.has_event(stored["id"], "delivered"):
                self._event(stored, "delivered", ts)
            self.store.mark_read(stored["id"])
        elif kind == "failed" and not self.store.has_event(stored["id"], "failed"):
            self._event(stored, "failed", ts, {"errors": status.get("errors", [])})
        else:
            return False
        return True

    def _whatsapp_inbound(self, message: dict[str, Any]) -> bool:
        wamid = message.get("id", "")
        if wamid and self.store.message_by_provider_id(wamid, "in"):
            return False  # duplicate delivery
        customer = self.store.customer_by_phone(message.get("from", ""))
        if customer is None:
            log.warning("inbound WhatsApp message from an unknown number was ignored")
            return False
        text = _text_of(message) or WHATSAPP_NON_TEXT
        self.svc.inbound(customer.id, "whatsapp", text, provider_id=wamid or None)
        return True

    # ------------------------------------------------------------------ SES
    def _ses(self, event: dict[str, Any], counts: dict[str, int]) -> None:
        kind = event.get("eventType") or event.get("notificationType")
        mail = event.get("mail", {})
        stored = self.store.message_by_provider_id(mail.get("messageId", ""), "out")
        if stored is None:
            counts["ignored"] += 1
            return
        if kind == "Delivery":
            if not self.store.has_event(stored["id"], "delivered"):
                self._event(stored, "delivered")
        elif kind == "Open":
            self.store.mark_read(stored["id"])
        elif kind == "Click":
            if not self.store.has_event(stored["id"], "clicked"):
                self._event(stored, "clicked")
        elif kind in {"Bounce", "Reject", "Complaint"}:
            bounce = event.get("bounce", {})
            permanent = kind != "Bounce" or bounce.get("bounceType") == "Permanent"
            self._event(stored, "failed", meta={"reason": kind})
            if permanent:
                # Never keep mailing an address that bounced or complained.
                self.store.set_consent(stored["customer_id"], "email", False)
        else:
            counts["ignored"] += 1
            return
        counts["receipts"] += 1

    # ------------------------------------------------------------------ helpers
    def _event(self, stored: dict[str, Any], type_: str, ts: str | None = None, meta: dict | None = None) -> None:
        self.store.log_event(
            stored["customer_id"], stored["channel"], type_, stored["thread_id"], stored["id"], meta, ts
        )


def _epoch_iso(value: Any) -> str | None:
    try:
        return iso(datetime.fromtimestamp(int(value), UTC))
    except (TypeError, ValueError, OverflowError):
        return None
