"""Runtime configuration, read from the environment once at startup."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _channels() -> tuple[str, ...]:
    raw = os.getenv("RENEWFLOW_CHANNELS", "whatsapp,email")
    return tuple(c.strip() for c in raw.split(",") if c.strip())


@dataclass(frozen=True)
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("RENEWFLOW_DB", "renewflow.db"))
    mode: str = field(default_factory=lambda: os.getenv("RENEWFLOW_MODE", "local"))
    model: str = field(default_factory=lambda: os.getenv("RENEWFLOW_MODEL", "mock"))
    enabled_channels: tuple[str, ...] = field(default_factory=_channels)
    base_url: str = field(
        default_factory=lambda: os.getenv("RENEWFLOW_BASE_URL", "http://localhost:8000")
    )
    max_proactive_per_day: int = 2
    quiet_start_hour: int = 21
    quiet_end_hour: int = 8
    max_agent_steps: int = 8
