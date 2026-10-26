"""Deterministic quote maths and rupee formatting.

The agent never calculates prices itself: every figure it may state comes from here,
via a tool result. That is what makes the "no invented prices" guardrail enforceable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# plan -> (number of payments, instalment loading as a fraction of the annual premium)
PLANS: dict[str, tuple[int, float]] = {
    "annual": (1, 0.00),
    "quarterly": (4, 0.03),
    "monthly": (12, 0.06),
}


@dataclass(frozen=True)
class Quote:
    plan: str
    installments: int
    per_installment: int
    total: int
    surcharge: int


def build_quote(annual_premium: int, plan: str) -> Quote:
    if plan not in PLANS:
        raise ValueError(f"unknown plan: {plan}")
    count, loading = PLANS[plan]
    loaded = int(annual_premium * (1 + loading) + 0.5)
    per = int(loaded / count + 0.5)
    total = per * count
    return Quote(plan, count, per, total, total - annual_premium)


def inr(amount: int) -> str:
    """Format with Indian digit grouping: 1850000 -> ₹18,50,000."""
    digits = str(abs(int(amount)))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        digits = f"{head},{tail}"
    return f"{'-' if amount < 0 else ''}₹{digits}"


_AMOUNT = re.compile(r"(?:₹|Rs\.?|INR)\s?(\d[\d,]*)")


def amounts_in(text: str) -> list[int]:
    """Every rupee amount mentioned in a piece of text."""
    return [int(m.replace(",", "")) for m in _AMOUNT.findall(text)]
