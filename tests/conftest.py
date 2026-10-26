from __future__ import annotations

from datetime import UTC, datetime

import pytest

from renewflow.clock import FixedClock
from renewflow.config import Settings
from renewflow.seed import seed_demo
from renewflow.service import RenewFlow

NOON_IST = datetime(2026, 10, 26, 6, 30, tzinfo=UTC)  # 12:00 in Asia/Kolkata
NIGHT_IST = datetime(2026, 10, 26, 17, 30, tzinfo=UTC)  # 23:00 in Asia/Kolkata


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOON_IST)


@pytest.fixture
def svc(clock: FixedClock) -> RenewFlow:
    service = RenewFlow.create(Settings(db_path=":memory:"), clock)
    seed_demo(service.store)
    return service


def outbound(svc: RenewFlow, thread_id: int) -> list[dict]:
    return [m for m in svc.store.thread_messages(thread_id) if m["direction"] == "out"]
