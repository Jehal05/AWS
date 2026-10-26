"""Read models for the dashboard: shape the data the way the UI wants it, mask what it shouldn't see."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..agent.guardrails import tz_for
from ..analytics import scoring
from ..privacy import mask_email, mask_phone
from ..service import RenewFlow


def _today(svc: RenewFlow):
    return svc.store.clock.now().astimezone(tz_for("Asia/Kolkata")).date()


def _status(policy_status: str, thread: dict[str, Any] | None, inbound: int) -> str:
    if policy_status == "renewed":
        return "renewed"
    if thread is None:
        return "not_contacted"
    if thread["status"] in ("handoff", "opted_out"):
        return thread["status"]
    return "in_conversation" if inbound else "contacted"


def customer_rows(svc: RenewFlow) -> list[dict[str, Any]]:
    store, db = svc.store, svc.store.db
    today = _today(svc)
    threads = {t["customer_id"]: t for t in db.query("SELECT * FROM threads ORDER BY id")}
    last = {
        m["thread_id"]: m
        for m in db.query(
            "SELECT m.* FROM messages m JOIN (SELECT MAX(id) mid FROM messages GROUP BY thread_id)"
            " x ON m.id = x.mid"
        )
    }
    inbound = {
        r["thread_id"]: r["n"]
        for r in db.query(
            "SELECT thread_id, COUNT(*) n FROM messages WHERE direction='in' GROUP BY thread_id"
        )
    }
    rows = []
    for customer in store.all_customers():
        policy = store.renewal_policy_for(customer.id)
        if policy is None:
            continue
        thread = threads.get(customer.id)
        tid = thread["id"] if thread else None
        message = last.get(tid) if tid else None
        ranked = scoring.rank_channels(store, customer.id, svc.settings.enabled_channels, store.clock.now())
        best, confidence = scoring.recommend(ranked)
        rows.append(
            {
                "id": customer.id,
                "name": customer.name,
                "segment": customer.persona,
                "policy_id": policy.id,
                "product": policy.product,
                "asset": policy.asset,
                "expiry_date": policy.expiry_date,
                "days_to_expiry": policy.days_to_expiry(today),
                "premium_new": policy.premium_new,
                "status": _status(policy.status, thread, inbound.get(tid, 0)),
                "best_channel": best.channel if best else None,
                "confidence": confidence,
                "last": (
                    {
                        "channel": message["channel"],
                        "direction": message["direction"],
                        "text": message["body"].replace("\n", " ")[:90],
                        "ts": message["created_at"],
                    }
                    if message else None
                ),
            }
        )
    return rows


def customer_detail(svc: RenewFlow, customer_id: int) -> dict[str, Any] | None:
    store, db = svc.store, svc.store.db
    customer = store.get_customer(customer_id)
    policy = store.renewal_policy_for(customer_id) if customer else None
    if customer is None or policy is None:
        return None
    now = store.clock.now()
    ranked = scoring.rank_channels(store, customer_id, svc.settings.enabled_channels, now)
    best, confidence = scoring.recommend(ranked)

    thread = store.thread_for(customer_id)
    messages: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    handoff = None
    if thread:
        read_ids = {
            r["message_id"]
            for r in db.query(
                "SELECT message_id FROM events WHERE thread_id=? AND type='read'", (thread["id"],)
            )
        }
        clicked_ids = {
            r["message_id"]
            for r in db.query(
                "SELECT message_id FROM events WHERE thread_id=? AND type='clicked'", (thread["id"],)
            )
        }
        for m in store.thread_messages(thread["id"]):
            messages.append(
                {
                    "id": m["id"], "channel": m["channel"], "direction": m["direction"],
                    "sender": m["sender"], "subject": m["subject"], "body": m["body"],
                    "created_at": m["created_at"], "kind": m["meta"].get("kind"),
                    "read": m["id"] in read_ids, "clicked": m["id"] in clicked_ids,
                }
            )
        trace = store.trace_for_thread(thread["id"])
        handoff = db.one(
            "SELECT * FROM handoffs WHERE thread_id=? ORDER BY id DESC LIMIT 1", (thread["id"],)
        )

    inbound = sum(1 for m in messages if m["direction"] == "in")
    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "email": mask_email(customer.email),
            "phone": mask_phone(customer.phone),
            "language": customer.language,
            "timezone": customer.timezone,
            "segment": customer.persona,
        },
        "policy": {
            **{k: v for k, v in asdict(policy).items()},
            "delta": policy.delta,
            "days_to_expiry": policy.days_to_expiry(_today(svc)),
        },
        "consents": store.consents(customer_id),
        "channels": {
            "recommended": best.channel if best else None,
            "confidence": confidence,
            "ranking": [s.to_dict() for s in ranked],
            "quiet_hours": svc.guardrails.quiet_hours(customer, now),
        },
        "thread": (
            {"id": thread["id"], "status": thread["status"]} if thread else None
        ),
        "status": _status(policy.status, thread, inbound),
        "messages": messages,
        "trace": trace,
        "handoff": handoff,
        "followups": store.followups_for(customer_id),
        "quotes": store.quotes_for_policy(policy.id),
    }
