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
    # Channels that stay simulated even in AWS mode, for example WhatsApp until Meta approves the
    # business. The dashboard shows the mix, so a simulated channel is never mistaken for a real one.
    local_channels: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            c.strip() for c in os.getenv("RENEWFLOW_LOCAL_CHANNELS", "").split(",") if c.strip()
        )
    )
    # AWS mode only. Nothing here is a secret; credentials come from the standard AWS chain.
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    wa_phone_number_id: str = field(default_factory=lambda: os.getenv("RENEWFLOW_WA_PHONE_ID", ""))
    wa_meta_version: str = field(default_factory=lambda: os.getenv("RENEWFLOW_WA_META_VERSION", "v20.0"))
    wa_template: str = field(default_factory=lambda: os.getenv("RENEWFLOW_WA_TEMPLATE", ""))
    wa_template_lang: str = field(default_factory=lambda: os.getenv("RENEWFLOW_WA_TEMPLATE_LANG", "en"))
    ses_from: str = field(default_factory=lambda: os.getenv("RENEWFLOW_SES_FROM", ""))
    ses_config_set: str = field(default_factory=lambda: os.getenv("RENEWFLOW_SES_CONFIG_SET", ""))
    bedrock_model_id: str = field(
        default_factory=lambda: os.getenv("RENEWFLOW_BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    )
    # Webhook hardening: SNS posts to /webhooks/sns/<token>, and only these topics are accepted.
    webhook_token: str = field(default_factory=lambda: os.getenv("RENEWFLOW_WEBHOOK_TOKEN", ""))
    sns_topic_arns: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            a.strip() for a in os.getenv("RENEWFLOW_SNS_TOPIC_ARNS", "").split(",") if a.strip()
        )
    )
    max_proactive_per_day: int = 2
    quiet_start_hour: int = 21
    quiet_end_hour: int = 8
    max_agent_steps: int = 8
