"""Safety checks that run on every outbound message, whichever model wrote it.

The model proposes; the guardrails decide. Each block has a short machine-readable reason
so the dashboard can show exactly what was stopped and why.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from ..channels.base import MAX_LENGTH
from ..clock import iso
from ..config import Settings
from ..pricing import amounts_in
from ..store import CHANNELS, Customer, Store

_OPT_OUT_EXACT = re.compile(
    r"^\s*(stop( all)?|unsubscribe|cancel|end|quit|opt[- ]?out)\s*[.!]*\s*$", re.IGNORECASE
)
_OPT_OUT_PHRASE = re.compile(
    r"\b(stop (messaging|texting|contacting|sending|emailing)|unsubscribe|"
    r"do not (contact|message)|don'?t (contact|message)|mat bhej\w*|bhejna band|message band|"
    r"band karo)\b|बंद करो|मत भेजो|मैसेज बंद",
    re.IGNORECASE,
)
_OPT_IN = re.compile(r"^\s*(start|subscribe|unstop|yes please start)\s*[.!]*\s*$", re.IGNORECASE)

_PROHIBITED = [
    (re.compile(r"\bguarantee[sd]?\b", re.IGNORECASE), "Messages must not promise or guarantee outcomes"),
    (re.compile(r"\b100\s?%\s?(claim|approval|settlement)", re.IGNORECASE), "No absolute claim promises"),
    (re.compile(r"\bno questions asked\b", re.IGNORECASE), "No absolute claim promises"),
]


def is_opt_out(text: str) -> bool:
    return bool(_OPT_OUT_EXACT.match(text) or _OPT_OUT_PHRASE.search(text))


def is_opt_in(text: str) -> bool:
    return bool(_OPT_IN.match(text))


def tz_for(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except Exception:  # tz database missing: fall back sensibly
        if name == "Asia/Kolkata":
            return timezone(timedelta(hours=5, minutes=30))
        return UTC


@dataclass
class Verdict:
    allowed: bool
    reason: str | None = None
    detail: str | None = None


def _block(reason: str, detail: str) -> Verdict:
    return Verdict(False, reason, detail)


class Guardrails:
    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.settings = settings

    def quiet_hours(self, customer: Customer, now: datetime) -> dict[str, Any]:
        """Is it outside the hours we may start a conversation, in the customer's timezone?"""
        start, end = self.settings.quiet_start_hour, self.settings.quiet_end_hour
        enforced = self.store.get_setting("quiet_hours", "on") == "on"
        local = now.astimezone(tz_for(customer.timezone))
        in_quiet = local.hour >= start or local.hour < end
        hours = 0
        if in_quiet:
            opens = local.replace(hour=end, minute=0, second=0, microsecond=0)
            if local.hour >= start:
                opens += timedelta(days=1)
            hours = math.ceil((opens - local).total_seconds() / 3600)
        return {
            "active": enforced and in_quiet,
            "enforced": enforced,
            "local_time": local.strftime("%H:%M"),
            "window": f"{end:02d}:00–{start:02d}:00",
            "hours_until_window": hours if enforced else 0,
        }

    def check_send(self, ctx: Any, channel: str, body: str, subject: str | None) -> Verdict:
        store = self.store
        if channel not in CHANNELS or channel not in self.settings.enabled_channels:
            return _block("channel_unavailable", f"{channel} is not enabled for this deployment")
        customer = store.get_customer(ctx.customer_id)
        if customer is None:
            return _block("unknown_customer", "Customer not found")
        if not ctx.exempt_consent and not store.consents(customer.id).get(channel):
            return _block("no_consent", f"{customer.first_name} has not opted in to {channel}")
        if len(body) > MAX_LENGTH[channel]:
            return _block("too_long", f"{len(body)} characters exceeds the {channel} limit")
        text = f"{subject or ''}\n{body}"
        for pattern, why in _PROHIBITED:
            if pattern.search(text):
                return _block("prohibited_claim", why)

        now = store.clock.now()
        if ctx.trigger == "proactive":
            quiet = self.quiet_hours(customer, now)
            if quiet["active"]:
                return _block(
                    "quiet_hours",
                    f"It is {quiet['local_time']} for the customer; messages start at "
                    f"{self.settings.quiet_end_hour:02d}:00",
                )
            recent = store.db.scalar(
                "SELECT COUNT(*) FROM messages WHERE customer_id=? AND direction='out'"
                " AND created_at>=? AND json_extract(meta,'$.proactive')=1",
                (customer.id, iso(now - timedelta(hours=24))),
            )
            if recent >= self.settings.max_proactive_per_day:
                return _block("rate_limit", f"{recent} proactive messages in the last 24 hours")

        ungrounded = sorted({a for a in amounts_in(text) if a not in ctx.allowed_amounts})
        if ungrounded:
            shown = ", ".join(f"₹{a:,}" for a in ungrounded)
            return _block("ungrounded_amount", f"Amount not returned by any tool: {shown}")
        return Verdict(True)
