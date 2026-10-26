"""AWS channel adapters: WhatsApp through AWS End User Messaging Social, email through SES.

Both return as soon as the provider accepts the message. Delivery, read and reply events arrive
later through the webhook (see ``renewflow.aws.webhook``), so ``delivered`` stays False here.
"""

from __future__ import annotations

import json
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from .base import OutboundMessage, SendResult


def _error(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        err = exc.response.get("Error", {})
        return f"{err.get('Code', 'ClientError')}: {err.get('Message', '')}".strip(": ")
    return f"{type(exc).__name__}: {exc}"


class AwsWhatsAppChannel:
    """Sends WhatsApp messages with ``socialmessaging:SendWhatsAppMessage``.

    WhatsApp only allows free-form text inside the 24 hour customer-service window. The opening
    message of a renewal is outside it, so it must be an approved template. When a template is
    configured it is used for proactive messages (its body takes the message text as {{1}});
    replies are sent as plain text.
    """

    name = "whatsapp"

    def __init__(
        self,
        client: Any,
        phone_number_id: str,
        meta_version: str = "v20.0",
        template: str = "",
        template_lang: str = "en",
    ):
        if not phone_number_id:
            raise ValueError("RENEWFLOW_WA_PHONE_ID is required for the WhatsApp channel")
        self.client = client
        self.phone_number_id = phone_number_id
        self.meta_version = meta_version
        self.template = template
        self.template_lang = template_lang

    def payload(self, message: OutboundMessage) -> dict[str, Any]:
        to = message.customer.phone
        base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}
        if self.template and message.meta.get("kind") == "proactive":
            return {
                **base,
                "type": "template",
                "template": {
                    "name": self.template,
                    "language": {"code": self.template_lang},
                    "components": [
                        {
                            "type": "body",
                            # Template parameters cannot contain newlines or long runs of spaces.
                            "parameters": [{"type": "text", "text": " ".join(message.body.split())}],
                        }
                    ],
                },
            }
        return {**base, "type": "text", "text": {"preview_url": False, "body": message.body}}

    def send(self, message: OutboundMessage) -> SendResult:
        if not message.customer.phone:
            return SendResult(ok=False, error="no whatsapp address on file")
        try:
            response = self.client.send_whatsapp_message(
                message=json.dumps(self.payload(message)).encode(),
                originationPhoneNumberId=self.phone_number_id,
                metaApiVersion=self.meta_version,
            )
        except (ClientError, BotoCoreError) as exc:
            return SendResult(ok=False, error=_error(exc))
        return SendResult(ok=True, provider_message_id=response.get("messageId"))


class SesEmailChannel:
    """Sends plain-text email with ``sesv2:SendEmail``."""

    name = "email"

    def __init__(self, client: Any, from_address: str, configuration_set: str = ""):
        if not from_address:
            raise ValueError("RENEWFLOW_SES_FROM is required for the email channel")
        self.client = client
        self.from_address = from_address
        self.configuration_set = configuration_set

    def request(self, message: OutboundMessage) -> dict[str, Any]:
        req: dict[str, Any] = {
            "FromEmailAddress": self.from_address,
            "Destination": {"ToAddresses": [message.customer.email]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": message.subject or "Your policy renewal", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": message.body, "Charset": "UTF-8"}},
                }
            },
            "EmailTags": [{"Name": "app", "Value": "renewflow"}],
        }
        if self.configuration_set:
            req["ConfigurationSetName"] = self.configuration_set
        return req

    def send(self, message: OutboundMessage) -> SendResult:
        if not message.customer.email:
            return SendResult(ok=False, error="no email address on file")
        try:
            response = self.client.send_email(**self.request(message))
        except (ClientError, BotoCoreError) as exc:
            return SendResult(ok=False, error=_error(exc))
        return SendResult(ok=True, provider_message_id=response.get("MessageId"))
