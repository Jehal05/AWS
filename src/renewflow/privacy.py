"""Masking for anything shown in a UI or placed in a model prompt."""

from __future__ import annotations

import re


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "—"
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}"


def mask_phone(phone: str | None) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 6:
        return "—"
    return f"+{digits[:2]} ••••• ••{digits[-3:]}"
