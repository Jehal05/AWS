"""Cohort simulation: scripted synthetic customers run through the real agent.

Nothing is mocked past the customer's own behaviour. Each simulated customer receives a real
proactive message, and every reply, quote, guardrail check and handoff is the production code
path. This is how the dashboard is filled with live numbers without inventing any.
"""

from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from .agent.guardrails import tz_for
from .clock import FixedClock

SCRIPTS: dict[str, list[tuple[str, str | None]]] = {
    "price_then_split": [
        ("reply", "Why has my premium gone up so much?"),
        ("reply", "Can I pay quarterly instead?"),
        ("reply", "Please email me the details"),
        ("read", None),
        ("pay", None),
    ],
    "explain_then_pay": [
        ("reply", "Premium looks higher than last year, why?"),
        ("reply", "Ok, send me the payment link"),
        ("pay", None),
    ],
    "quick_renew": [("reply", "Yes, let's renew"), ("pay", None)],
    "monthly_plan": [
        ("reply", "Can I pay monthly? The premium looks too high"),
        ("reply", "Sure, go ahead"),
        ("pay", None),
    ],
    "claim_dispute": [
        ("reply", "My claim was rejected last year and nobody helped. I want to speak to a person."),
    ],
    "opt_out": [("reply", "STOP")],
    "reader_only": [("read", None)],
    "ghost": [],
    "confused": [("reply", "hmm what is this about"), ("reply", "no idea what this is")],
}

WEIGHTS: dict[str, dict[str, int]] = {
    "whatsapp_first": {"price_then_split": 22, "explain_then_pay": 18, "quick_renew": 16,
                       "monthly_plan": 8, "claim_dispute": 5, "opt_out": 2, "reader_only": 14,
                       "ghost": 11, "confused": 4},
    "email_first": {"price_then_split": 10, "explain_then_pay": 14, "quick_renew": 12,
                    "monthly_plan": 6, "claim_dispute": 4, "opt_out": 3, "reader_only": 25,
                    "ghost": 22, "confused": 4},
    "balanced": {"price_then_split": 14, "explain_then_pay": 14, "quick_renew": 12,
                 "monthly_plan": 6, "claim_dispute": 5, "opt_out": 3, "reader_only": 20,
                 "ghost": 22, "confused": 4},
    "low_engagement": {"price_then_split": 4, "explain_then_pay": 6, "quick_renew": 6,
                       "monthly_plan": 2, "claim_dispute": 4, "opt_out": 6, "reader_only": 22,
                       "ghost": 46, "confused": 4},
}


def _base_time(now: datetime, hours_needed: int = 5) -> datetime:
    """10:00 IST on the most recent day that leaves room before 'now', so nothing is future-dated."""
    local = now.astimezone(tz_for("Asia/Kolkata"))
    base = local.replace(hour=10, minute=0, second=0, microsecond=0)
    if base + timedelta(hours=hours_needed) > local:
        base -= timedelta(days=1)
    return base.astimezone(now.tzinfo)


def run_cohort(svc: Any, count: int, rng_seed: int | None = None, exclude: set[int] | None = None):
    store = svc.store
    rng = random.Random(rng_seed)
    exclude = exclude if exclude is not None else {1}
    candidates = []
    for customer in store.all_customers():
        policy = store.renewal_policy_for(customer.id)
        if customer.id in exclude or policy is None or policy.status != "open":
            continue
        if store.thread_for(customer.id) is None:
            candidates.append(customer)
    rng.shuffle(candidates)
    chosen = candidates[: max(0, count)]

    real_clock = store.clock
    sim = FixedClock(_base_time(real_clock.now()))
    base = sim.now()
    scenarios: Counter[str] = Counter()
    with svc.agent.global_lock:
        store.clock = sim
        try:
            for index, customer in enumerate(chosen):
                sim.set(base + timedelta(minutes=index * 2 + rng.randint(0, 5)))
                weights = WEIGHTS.get(customer.persona, WEIGHTS["balanced"])
                scenario = rng.choices(list(weights), weights=list(weights.values()))[0]
                _play(svc, customer, scenario, sim, rng)
                scenarios[scenario] += 1
        finally:
            store.clock = real_clock
    return {"customers": len(chosen), "scenarios": dict(scenarios)}


def _play(svc: Any, customer: Any, scenario: str, sim: FixedClock, rng: random.Random) -> None:
    store = svc.store
    policy = store.renewal_policy_for(customer.id)
    svc.start_renewal(policy.id)
    for action, text in SCRIPTS[scenario]:
        sim.advance(minutes=rng.randint(1, 12))
        thread = store.thread_for(customer.id)
        if thread is None or thread["status"] in ("handoff", "opted_out"):
            return
        outbound = [m for m in store.thread_messages(thread["id"]) if m["direction"] == "out"]
        if action == "read" and outbound:
            store.mark_read(outbound[-1]["id"])
        elif action == "reply" and outbound:
            svc.inbound(customer.id, outbound[-1]["channel"], text)
        elif action == "pay":
            quote = store.latest_quote(policy.id)
            if quote and quote.message_id:  # the customer can only pay a link they received
                svc.pay(quote.token)
