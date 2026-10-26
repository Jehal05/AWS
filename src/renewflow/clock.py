"""Injectable time, so tests and the cohort simulator can control it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

UTC = UTC


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock(Clock):
    """A clock that only moves when told to."""

    def __init__(self, start: datetime):
        self._now = start

    def now(self) -> datetime:
        return self._now

    def set(self, value: datetime) -> None:
        self._now = value

    def advance(self, **kwargs: float) -> None:
        self._now += timedelta(**kwargs)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
