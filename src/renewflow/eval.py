"""Run the golden conversations against a model and print the pass rate.

    python -m renewflow.eval                    # rule-based mock
    RENEWFLOW_MODEL=bedrock python -m renewflow.eval   # live Bedrock (needs AWS access)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from .clock import FixedClock
from .config import Settings
from .evalset import CASES, Case
from .seed import seed_demo
from .service import RenewFlow

NOON_IST = datetime(2026, 10, 26, 6, 30, tzinfo=UTC)


@dataclass
class Result:
    case: Case
    got: str

    @property
    def passed(self) -> bool:
        return self.got == self.case.expect


def observe(svc: RenewFlow, thread_id: int, run) -> str:
    """Reduce what the agent did to one of the labelled outcomes."""
    if svc.store.consents(1).get("whatsapp") is False:
        return "optout"
    if run.handoff or run.outcome == "handoff":
        return "handoff"
    out = [m for m in svc.store.thread_messages(thread_id) if m["direction"] == "out"][1:]
    if any(m["channel"] == "email" for m in out):
        return "email"
    last = out[-1]["body"] if out else ""
    if "/pay/" in last:
        return "pay_link"
    return "answer" if "₹" in last else "clarify"


def run_case(case: Case, settings: Settings | None = None) -> Result:
    svc = RenewFlow.create(settings or Settings(db_path=":memory:"), FixedClock(NOON_IST))
    seed_demo(svc.store)
    first = svc.start_renewal(1)
    run = svc.inbound(1, "whatsapp", case.text)
    return Result(case, observe(svc, first.thread_id, run))


def run_all(settings: Settings | None = None) -> list[Result]:
    return [run_case(c, settings) for c in CASES]


def main() -> int:
    settings = Settings(db_path=":memory:")
    results = run_all(settings)
    for r in results:
        if not r.passed:
            print(f"FAIL [{r.case.tag}] {r.case.text!r}: expected {r.case.expect}, got {r.got}")
    by_tag: dict[str, list[bool]] = {}
    for r in results:
        by_tag.setdefault(r.case.tag, []).append(r.passed)
    passed = sum(r.passed for r in results)
    print(f"\nmodel={settings.model}  passed {passed}/{len(results)}")
    for tag, flags in sorted(by_tag.items()):
        print(f"  {tag:9} {sum(flags)}/{len(flags)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
