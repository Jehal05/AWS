"""Builds the channel adapters for the configured mode."""

from __future__ import annotations

from ..config import Settings
from .base import Channel
from .local import LocalChannel


def build_channels(settings: Settings) -> dict[str, Channel]:
    if settings.mode == "local":
        return {name: LocalChannel(name) for name in settings.enabled_channels}
    if settings.mode == "aws":
        raise NotImplementedError(
            "AWS channel adapters (EUM Social, SES) arrive in the AWS integration step."
        )
    raise ValueError(f"unknown RENEWFLOW_MODE: {settings.mode!r}")
