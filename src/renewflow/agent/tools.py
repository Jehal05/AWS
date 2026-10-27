"""The tools the agent may call. Each returns a plain dict that is also the audit record."""

from __future__ import annotations

import inspect
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from ..analytics import scoring
from ..channels.base import Channel, OutboundMessage
from ..clock import iso
from ..config import Settings
from ..pricing import PLANS, build_quote
from ..privacy import mask_email
from ..store import CHANNELS, Store
from .guardrails import Guardrails, tz_for

MESSAGE_KINDS = {"proactive", "info", "clarify", "quote", "handoff", "confirmation"}


@dataclass
class ToolContext:
    store: Store
    channels: dict[str, Channel]
    guardrails: Guardrails
    settings: Settings
    customer_id: int
    thread_id: int
    run_id: int
    trigger: str  # "proactive" | "inbound"
    inbound_channel: str | None = None
    exempt_consent: bool = False
    allowed_amounts: set[int] = field(default_factory=set)
    sent: list[dict[str, Any]] = field(default_factory=list)
    blocked: list[dict[str, Any]] = field(default_factory=list)
    scheduled: list[int] = field(default_factory=list)
    handoff_created: bool = False

    def allow(self, *amounts: int) -> None:
        self.allowed_amounts.update(int(a) for a in amounts)


# --------------------------------------------------------------------------- tools
def lookup_policy(ctx: ToolContext, policy_id: int | None = None) -> dict[str, Any]:
    """Facts about the customer's renewal. The only source of premium figures."""
    store = ctx.store
    policy = store.get_policy(int(policy_id)) if policy_id else store.renewal_policy_for(ctx.customer_id)
    if policy is None or policy.customer_id != ctx.customer_id:
        return {"ok": False, "error": "policy_not_found"}
    customer = store.get_customer(ctx.customer_id)
    today = store.clock.now().astimezone(tz_for(customer.timezone)).date()
    reasons = [{"label": r["label"], "amount": int(r["amount"])} for r in policy.increase_reasons]
    ctx.allow(
        policy.premium_prev, policy.premium_new, abs(policy.delta), policy.sum_insured,
        *[r["amount"] for r in reasons],
    )

    latest = None
    quote = store.latest_quote(policy.id)
    if quote:
        ctx.allow(quote.per_installment, quote.total, quote.surcharge)
        latest = {
            "plan": quote.plan, "installments": quote.installments,
            "per_installment": quote.per_installment, "total": quote.total,
            "surcharge": quote.surcharge,
            "link": f"{ctx.settings.base_url.rstrip('/')}/pay/{quote.token}",
        }

    recent = store.thread_messages(ctx.thread_id)[-6:]
    clarifications = sum(
        1 for m in recent if m["direction"] == "out" and m["meta"].get("kind") == "clarify"
    )
    return {
        "ok": True,
        "policy_id": policy.id,
        "policy_number": policy.policy_number,
        "product": policy.product,
        "asset": policy.asset,
        "expiry_date": policy.expiry_date,
        "days_to_expiry": policy.days_to_expiry(today),
        "premium_prev": policy.premium_prev,
        "premium_new": policy.premium_new,
        "delta": policy.delta,
        "increase_reasons": reasons,
        "ncb_percent": policy.ncb_percent,
        "sum_insured": policy.sum_insured,
        "status": policy.status,
        "first_name": customer.first_name,
        "email_masked": mask_email(customer.email) if customer.email else None,
        "consents": store.consents(customer.id),
        "latest_quote": latest,
        "clarifications_sent": clarifications,
    }


def generate_quote(ctx: ToolContext, plan: str) -> dict[str, Any]:
    """Price a payment plan and create a payment link. Deterministic; never an estimate."""
    store = ctx.store
    policy = store.renewal_policy_for(ctx.customer_id)
    if policy is None or policy.status != "open":
        return {"ok": False, "error": "policy_not_open_for_renewal"}
    if plan not in PLANS:
        return {"ok": False, "error": f"plan must be one of {sorted(PLANS)}"}
    quote = build_quote(policy.premium_new, plan)
    token = secrets.token_urlsafe(8)
    store.add_quote(policy.id, ctx.thread_id, quote, token)
    ctx.allow(quote.per_installment, quote.total, quote.surcharge, policy.premium_new)
    return {
        "ok": True,
        "plan": quote.plan,
        "installments": quote.installments,
        "per_installment": quote.per_installment,
        "total": quote.total,
        "surcharge": quote.surcharge,
        "annual_premium": policy.premium_new,
        "link": f"{ctx.settings.base_url.rstrip('/')}/pay/{token}",
    }


BASELINE_CHANNEL = "email"  # what most renewal teams do today: email everyone first


def next_best_channel(ctx: ToolContext, purpose: str = "renewal") -> dict[str, Any]:
    """Rank the customer's channels from their engagement history."""
    store = ctx.store
    customer = store.get_customer(ctx.customer_id)
    now = store.clock.now()
    ranked = scoring.rank_channels(store, customer.id, ctx.settings.enabled_channels, now)
    best, confidence = scoring.recommend(ranked)
    eligible = [s for s in ranked if s.eligible]
    if store.get_setting(f"arm:{customer.id}", "smart") == "baseline":
        # Experiment control group: the fixed default channel, ignoring engagement history.
        fixed = next((s for s in eligible if s.channel == BASELINE_CHANNEL), None)
        if fixed is not None:
            best, confidence = fixed, "baseline"
            eligible = [fixed] + [s for s in eligible if s is not fixed]
    fallback = eligible[1].channel if len(eligible) > 1 else None
    return {
        "ok": True,
        "recommended": best.channel if best else None,
        "confidence": confidence,
        "fallback": fallback,
        "ranking": [s.to_dict() for s in ranked],
        "quiet_hours": ctx.guardrails.quiet_hours(customer, now),
    }


def send_message(
    ctx: ToolContext, channel: str, body: str, subject: str | None = None, kind: str = "info"
) -> dict[str, Any]:
    """Send a message to the customer. Every guardrail runs before anything leaves."""
    store = ctx.store
    kind = kind if kind in MESSAGE_KINDS else "info"
    verdict = ctx.guardrails.check_send(ctx, channel, body, subject)
    if not verdict.allowed:
        store.log_event(
            ctx.customer_id, channel if channel in CHANNELS else "-", "blocked", ctx.thread_id,
            meta={"reason": verdict.reason, "detail": verdict.detail},
        )
        ctx.blocked.append({"channel": channel, "reason": verdict.reason, "detail": verdict.detail})
        return {"ok": False, "blocked_by": verdict.reason, "detail": verdict.detail}

    customer = store.get_customer(ctx.customer_id)
    result = ctx.channels[channel].send(
        OutboundMessage(customer, channel, body, subject, {"kind": kind})
    )
    if not result.ok:
        store.log_event(
            customer.id, channel, "failed", ctx.thread_id, meta={"error": result.error}
        )
        return {"ok": False, "error": result.error}

    message_id = store.add_message(
        ctx.thread_id, customer.id, channel, "out", "agent", body, subject,
        {
            "kind": kind,
            "provider_id": result.provider_message_id,
            "proactive": ctx.trigger == "proactive",
            "run_id": ctx.run_id,
        },
    )
    store.log_event(customer.id, channel, "sent", ctx.thread_id, message_id)
    if result.delivered:
        store.log_event(customer.id, channel, "delivered", ctx.thread_id, message_id)
    for token in re.findall(r"/pay/([\w-]+)", body):
        store.attach_quote_message(token, message_id)
    ctx.sent.append({"channel": channel, "message_id": message_id, "kind": kind})
    return {"ok": True, "message_id": message_id, "channel": channel}


def schedule_followup(ctx: ToolContext, hours: int, channel: str, note: str) -> dict[str, Any]:
    """Schedule a follow-up for later (for example when there has been no reply)."""
    hours = int(hours)
    if not 1 <= hours <= 168:
        return {"ok": False, "error": "hours must be between 1 and 168"}
    if channel not in ctx.settings.enabled_channels:
        return {"ok": False, "error": f"{channel} is not an enabled channel"}
    due = ctx.store.clock.now() + timedelta(hours=hours)
    followup_id = ctx.store.add_followup(
        ctx.thread_id, ctx.customer_id, channel, iso(due), note[:200]
    )
    ctx.scheduled.append(followup_id)
    return {"ok": True, "followup_id": followup_id, "due_at": iso(due)}


def handoff_to_human(ctx: ToolContext, reason: str, summary: str) -> dict[str, Any]:
    """Pause the agent and queue the conversation for a person, with context."""
    handoff_id = ctx.store.add_handoff(ctx.thread_id, ctx.customer_id, reason[:300], summary[:1000])
    ctx.handoff_created = True
    return {"ok": True, "handoff_id": handoff_id}


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "lookup_policy": lookup_policy,
    "generate_quote": generate_quote,
    "next_best_channel": next_best_channel,
    "send_message": send_message,
    "schedule_followup": schedule_followup,
    "handoff_to_human": handoff_to_human,
}

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "lookup_policy",
        "description": "Get the customer's renewal policy: premium, last year's premium, the "
        "reasons it changed, expiry date, consents and any existing quote. The only source of "
        "premium figures.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "generate_quote",
        "description": "Price a payment plan (annual, quarterly or monthly) and create a payment "
        "link. Instalment plans include a disclosed instalment charge.",
        "input_schema": {
            "type": "object",
            "properties": {"plan": {"type": "string", "enum": ["annual", "quarterly", "monthly"]}},
            "required": ["plan"],
        },
    },
    {
        "name": "next_best_channel",
        "description": "Rank the customer's channels by past engagement and report whether quiet "
        "hours apply. Use before starting a conversation.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "send_message",
        "description": "Send a message to the customer on a channel. The only way to contact them. "
        "Blocked if consent is missing, quiet hours apply, or an amount was not returned by a tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "enum": list(CHANNELS)},
                "body": {"type": "string"},
                "subject": {"type": "string", "description": "Email only."},
                "kind": {"type": "string", "enum": sorted(MESSAGE_KINDS)},
            },
            "required": ["channel", "body"],
        },
    },
    {
        "name": "schedule_followup",
        "description": "Schedule a follow-up message for later (1 to 168 hours from now).",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer"},
                "channel": {"type": "string", "enum": list(CHANNELS)},
                "note": {"type": "string"},
            },
            "required": ["hours", "channel", "note"],
        },
    },
    {
        "name": "handoff_to_human",
        "description": "Hand the conversation to a person with a summary. Use for claims, "
        "complaints, disputes, requests for a person, or when unsure.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["reason", "summary"],
        },
    },
]


def execute_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run a tool defensively: unknown tools, bad arguments and exceptions become results."""
    func = TOOLS.get(name)
    if func is None:
        return {"ok": False, "error": f"unknown tool: {name}"}
    params = inspect.signature(func).parameters
    kwargs = {k: v for k, v in (arguments or {}).items() if k in params and k != "ctx"}
    missing = [
        p for p, spec in params.items()
        if p != "ctx" and spec.default is inspect.Parameter.empty and p not in kwargs
    ]
    if missing:
        return {"ok": False, "error": f"missing arguments: {', '.join(missing)}"}
    try:
        return func(ctx, **kwargs)
    except Exception as exc:  # a tool must never take the whole run down
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
