"""Channel-preference scoring: which channel is this customer most likely to engage on?

Every message event (sent, delivered, read, replied, clicked) feeds a per-customer,
per-channel score. Recent behaviour counts more (30-day half-life) and rates are
smoothed towards a neutral prior so one lucky read does not look like a trend.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from ..clock import parse_iso
from ..store import CHANNELS, Store

HALF_LIFE_DAYS = 30.0
PRIOR_STRENGTH = 2.0
PRIORS = {"read": 0.25, "reply": 0.10, "click": 0.10, "delivery": 0.90}
WEIGHTS = {"read": 0.45, "reply": 0.30, "click": 0.15, "delivery": 0.10}


@dataclass
class ChannelScore:
    channel: str
    score: float
    consent: bool
    enabled: bool
    sent: int
    delivered: int
    read: int
    replied: int
    clicked: int
    last_engaged: str | None
    reasons: list[str] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return self.consent and self.enabled

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = round(self.score, 3)
        data["eligible"] = self.eligible
        return data


def _smoothed(successes: float, trials: float, prior: float) -> float:
    return (successes + prior * PRIOR_STRENGTH) / (trials + PRIOR_STRENGTH)


def _ago(then: datetime, now: datetime) -> str:
    days = (now - then).days
    if days <= 0:
        return "today"
    return "1 day ago" if days == 1 else f"{days} days ago"


def rank_channels(
    store: Store, customer_id: int, enabled: tuple[str, ...], now: datetime
) -> list[ChannelScore]:
    consents = store.consents(customer_id)
    events = store.events_for(customer_id)
    ranked: list[ChannelScore] = []
    for channel in CHANNELS:
        weighted = {"sent": 0.0, "delivered": 0.0, "read": 0.0, "replied": 0.0, "clicked": 0.0}
        raw = {key: 0 for key in weighted}
        last_engaged: datetime | None = None
        for e in events:
            if e["channel"] != channel or e["type"] not in weighted:
                continue
            when = parse_iso(e["ts"])
            age_days = max((now - when).total_seconds() / 86400, 0.0)
            weighted[e["type"]] += 0.5 ** (age_days / HALF_LIFE_DAYS)
            raw[e["type"]] += 1
            if e["type"] in ("read", "replied", "clicked") and (
                last_engaged is None or when > last_engaged
            ):
                last_engaged = when

        read = _smoothed(weighted["read"], weighted["delivered"], PRIORS["read"])
        reply = _smoothed(weighted["replied"], weighted["delivered"], PRIORS["reply"])
        click = _smoothed(weighted["clicked"], weighted["delivered"], PRIORS["click"])
        delivery = _smoothed(weighted["delivered"], weighted["sent"], PRIORS["delivery"])
        score = (
            WEIGHTS["read"] * read
            + WEIGHTS["reply"] * reply
            + WEIGHTS["click"] * click
            + WEIGHTS["delivery"] * delivery
        )

        reasons: list[str] = []
        if raw["sent"] == 0:
            reasons.append("No history on this channel yet")
        else:
            reasons.append(f"Read {raw['read']} of {raw['delivered']} delivered")
            if raw["replied"]:
                reasons.append(f"Replied {raw['replied']} time{'s' if raw['replied'] != 1 else ''}")
            if raw["clicked"]:
                reasons.append(f"Clicked {raw['clicked']} link{'s' if raw['clicked'] != 1 else ''}")
            if last_engaged:
                reasons.append(f"Last engaged {_ago(last_engaged, now)}")
        if not consents.get(channel):
            reasons.append("No consent on file")
        if channel not in enabled:
            reasons.append("Channel not enabled for this deployment")

        ranked.append(
            ChannelScore(
                channel=channel,
                score=score,
                consent=consents.get(channel, False),
                enabled=channel in enabled,
                sent=raw["sent"],
                delivered=raw["delivered"],
                read=raw["read"],
                replied=raw["replied"],
                clicked=raw["clicked"],
                last_engaged=last_engaged.isoformat(timespec="seconds") if last_engaged else None,
                reasons=reasons,
            )
        )

    order = {c: i for i, c in enumerate(CHANNELS)}
    ranked.sort(key=lambda s: (-s.score, order[s.channel]))
    return ranked


def recommend(ranked: list[ChannelScore]) -> tuple[ChannelScore | None, str]:
    """Best eligible channel plus a plain-language confidence label."""
    eligible = [s for s in ranked if s.eligible]
    if not eligible:
        return None, "none"
    best = eligible[0]
    gap = best.score - eligible[1].score if len(eligible) > 1 else 1.0
    if best.delivered >= 5 and gap >= 0.15:
        return best, "high"
    if best.delivered >= 2:
        return best, "medium"
    return best, "low"
