"""Dashboard numbers, computed live from the event log. Nothing here is hard-coded."""

from __future__ import annotations

import json
import statistics
from typing import Any

from ..config import Settings
from ..store import CHANNELS, Store


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def overview(store: Store, settings: Settings) -> dict[str, Any]:
    db = store.db
    targeted = db.scalar("SELECT COUNT(*) FROM policies") or 0
    contacted = db.scalar("SELECT COUNT(DISTINCT customer_id) FROM messages WHERE direction='out'") or 0
    engaged = db.scalar(
        "SELECT COUNT(DISTINCT e.customer_id) FROM events e JOIN messages m ON m.id=e.message_id"
        " WHERE e.type='read' AND m.direction='out'"
    ) or 0
    replied = db.scalar("SELECT COUNT(DISTINCT customer_id) FROM messages WHERE direction='in'") or 0
    quoted = db.scalar("SELECT COUNT(DISTINCT policy_id) FROM quotes") or 0
    renewed = db.scalar("SELECT COUNT(*) FROM policies WHERE status='renewed'") or 0
    revenue = db.scalar("SELECT COALESCE(SUM(renewed_amount),0) FROM policies WHERE status='renewed'") or 0

    handoff_customers = db.scalar("SELECT COUNT(DISTINCT customer_id) FROM handoffs") or 0
    open_handoffs = db.scalar("SELECT COUNT(*) FROM handoffs WHERE status='open'") or 0
    opt_outs = db.scalar("SELECT COUNT(DISTINCT customer_id) FROM events WHERE type='opt_out'") or 0
    cross_channel = db.scalar(
        "SELECT COUNT(*) FROM (SELECT thread_id FROM messages GROUP BY thread_id"
        " HAVING COUNT(DISTINCT channel) > 1)"
    ) or 0
    followups = db.scalar("SELECT COUNT(*) FROM followups WHERE status='scheduled'") or 0

    latencies = [
        r["duration_ms"]
        for r in db.query(
            "SELECT duration_ms FROM agent_runs WHERE trigger='inbound' AND outcome NOT IN"
            " ('running','awaiting_human','opted_out') AND steps > 0"
        )
    ]
    median_ms = int(statistics.median(latencies)) if latencies else None

    funnel_counts = [
        ("targeted", "Policies due", targeted),
        ("contacted", "Contacted", contacted),
        ("engaged", "Opened a message", engaged),
        ("replied", "Replied", replied),
        ("quoted", "Got a quote", quoted),
        ("renewed", "Renewed", renewed),
    ]
    funnel = [
        {"key": k, "label": label, "count": n, "share": _rate(n, targeted)}
        for k, label, n in funnel_counts
    ]

    # What the agent has sent this campaign, per channel.
    sent = {r["channel"]: r["n"] for r in db.query(
        "SELECT channel, COUNT(*) n FROM messages WHERE direction='out' GROUP BY channel")}
    read = {r["channel"]: r["n"] for r in db.query(
        "SELECT m.channel, COUNT(DISTINCT m.id) n FROM messages m JOIN events e"
        " ON e.message_id=m.id AND e.type='read' WHERE m.direction='out' GROUP BY m.channel")}
    inbound = {r["channel"]: r["n"] for r in db.query(
        "SELECT channel, COUNT(*) n FROM messages WHERE direction='in' GROUP BY channel")}
    campaign = [
        {
            "channel": c,
            "sent": sent.get(c, 0),
            "read": read.get(c, 0),
            "replies": inbound.get(c, 0),
            "read_rate": _rate(read.get(c, 0), sent.get(c, 0)),
        }
        for c in CHANNELS if c in settings.enabled_channels
    ]

    # What the channel scores learn from: the 90-day engagement history (no message rows).
    hist: dict[str, dict[str, int]] = {c: {} for c in CHANNELS}
    for r in db.query(
        "SELECT channel, type, COUNT(*) n FROM events WHERE message_id IS NULL"
        " AND type IN ('delivered','read','replied') GROUP BY channel, type"
    ):
        if r["channel"] in hist:
            hist[r["channel"]][r["type"]] = r["n"]
    history = [
        {
            "channel": c,
            "delivered": hist[c].get("delivered", 0),
            "read_rate": _rate(hist[c].get("read", 0), hist[c].get("delivered", 0)),
            "reply_rate": _rate(hist[c].get("replied", 0), hist[c].get("delivered", 0)),
        }
        for c in CHANNELS if c in settings.enabled_channels
    ]

    reasons: dict[str, int] = {}
    for r in db.query("SELECT meta FROM events WHERE type='blocked'"):
        reason = json.loads(r["meta"]).get("reason", "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1

    return {
        "kpis": {
            "renewal_rate": _rate(renewed, contacted),
            "renewed": renewed,
            "contacted": contacted,
            "revenue_secured": revenue,
            "handled_without_human": _rate(replied - handoff_customers, replied),
            "median_response_ms": median_ms,
            "open_handoffs": open_handoffs,
            "cross_channel_threads": cross_channel,
            "opt_outs": opt_outs,
            "followups_scheduled": followups,
        },
        "funnel": funnel,
        "campaign_channels": campaign,
        "engagement_history": history,
        "guardrails": {"blocked_total": sum(reasons.values()), "by_reason": reasons},
        "activity": _activity(store),
    }


def _activity(store: Store, limit: int = 14) -> list[dict[str, Any]]:
    db = store.db
    names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM customers")}
    items: list[dict[str, Any]] = []
    for m in db.query("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit * 2,)):
        incoming = m["direction"] == "in"
        items.append({
            "ts": m["created_at"], "kind": "message_in" if incoming else "message_out",
            "customer_id": m["customer_id"], "name": names.get(m["customer_id"], "?"),
            "channel": m["channel"], "text": m["body"].replace("\n", " ")[:110],
        })
    labels = {"renewed": "Renewed", "handoff": "Handed to a person", "opt_out": "Opted out",
              "blocked": "Message blocked"}
    for e in db.query(
        "SELECT * FROM events WHERE type IN ('renewed','handoff','opt_out','blocked')"
        " ORDER BY id DESC LIMIT ?", (limit * 2,)
    ):
        meta = json.loads(e["meta"])
        detail = meta.get("detail") or meta.get("reason") or (
            f"{meta['plan']} plan" if e["type"] == "renewed" and meta.get("plan") else "")
        items.append({
            "ts": e["ts"], "kind": e["type"], "customer_id": e["customer_id"],
            "name": names.get(e["customer_id"], "?"), "channel": e["channel"],
            "text": f"{labels[e['type']]}" + (f": {detail}" if detail else ""),
        })
    items.sort(key=lambda i: i["ts"], reverse=True)
    return items[:limit]
