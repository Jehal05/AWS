"""HTTP entry point for Amazon SNS. SNS posts JSON with a text/plain content type.

The URL carries a secret token (so strangers cannot inject customer messages) and only messages
from allow-listed topics are processed. For production, also verify the SNS message signature.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import urllib.request

from fastapi import APIRouter, HTTPException, Request

from ..aws.events import AwsEventProcessor
from ..config import Settings
from ..service import RenewFlow

log = logging.getLogger("renewflow.webhooks")
SNS_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$")


def _confirm_subscription(url: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or not SNS_HOST.match(parsed.hostname or ""):
        raise HTTPException(400, "subscribe URL is not an SNS endpoint")
    with urllib.request.urlopen(url, timeout=10):
        pass


def build_router(svc: RenewFlow, settings: Settings) -> APIRouter:
    router = APIRouter()
    processor = AwsEventProcessor(svc)

    @router.post("/webhooks/sns/{token}")
    async def sns(token: str, request: Request):
        if not settings.webhook_token or not hmac.compare_digest(token, settings.webhook_token):
            raise HTTPException(404)  # indistinguishable from a route that does not exist
        try:
            envelope = json.loads(await request.body())
        except ValueError as exc:
            raise HTTPException(400, "body is not JSON") from exc
        topic = envelope.get("TopicArn", "")
        if settings.sns_topic_arns and topic not in settings.sns_topic_arns:
            raise HTTPException(403, "topic not allowed")
        kind = envelope.get("Type")
        if kind == "SubscriptionConfirmation":
            _confirm_subscription(envelope.get("SubscribeURL", ""))
            return {"ok": True, "confirmed": True}
        if kind != "Notification":
            return {"ok": True, "ignored": kind}
        try:
            message = json.loads(envelope.get("Message", "{}"))
        except ValueError as exc:
            raise HTTPException(400, "Message is not JSON") from exc
        counts = processor.process(message)
        log.info("sns notification processed: %s", counts)
        return {"ok": True, **counts}

    return router
