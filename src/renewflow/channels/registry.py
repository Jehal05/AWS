"""Builds the channel adapters for the configured mode."""

from __future__ import annotations

from ..config import Settings
from .base import Channel
from .local import LocalChannel


def build_channels(settings: Settings) -> dict[str, Channel]:
    if settings.mode == "local":
        return {name: LocalChannel(name) for name in settings.enabled_channels}
    if settings.mode == "aws":
        return _aws_channels(settings)
    raise ValueError(f"unknown RENEWFLOW_MODE: {settings.mode!r}")


def _aws_channels(settings: Settings) -> dict[str, Channel]:
    import boto3  # imported lazily so local mode never needs it

    from .aws import AwsWhatsAppChannel, SesEmailChannel

    channels: dict[str, Channel] = {}
    for name in settings.enabled_channels:
        if name in settings.local_channels:
            channels[name] = LocalChannel(name)
        elif name == "whatsapp":
            channels[name] = AwsWhatsAppChannel(
                boto3.client("socialmessaging", region_name=settings.aws_region),
                settings.wa_phone_number_id,
                settings.wa_meta_version,
                settings.wa_template,
                settings.wa_template_lang,
            )
        elif name == "email":
            channels[name] = SesEmailChannel(
                boto3.client("sesv2", region_name=settings.aws_region),
                settings.ses_from,
                settings.ses_config_set,
            )
        else:
            raise ValueError(f"channel {name!r} has no AWS adapter yet (enable whatsapp, email)")
    return channels
