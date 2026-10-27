"""Inbound events from WhatsApp (via SNS) and SES, using payloads shaped like the AWS docs."""

import dataclasses
import json

from conftest import outbound
from fastapi.testclient import TestClient

from renewflow.api.app import create_app
from renewflow.aws.events import AwsEventProcessor


def _wa_event(*, statuses=(), messages=()):
    entry = {
        "id": "503131219501234",
        "changes": [{"value": {"messaging_product": "whatsapp", "statuses": list(statuses), "messages": list(messages)}}],
    }
    return {"context": {}, "whatsAppWebhookEntry": json.dumps(entry), "messageId": "sns-1"}


def _phone(svc):
    return "".join(c for c in svc.store.get_customer(1).phone if c.isdigit())


def _opening(svc):
    result = svc.start_renewal(1)
    message = outbound(svc, result.thread_id)[0]
    return message, message["meta"]["provider_id"]


def test_receipts_become_delivered_and_read_events_once(svc):
    message, wamid = _opening(svc)
    proc = AwsEventProcessor(svc)
    delivered = {"id": wamid, "status": "delivered", "timestamp": "1736379042", "recipient_id": _phone(svc)}
    read = {**delivered, "status": "read"}
    for _ in range(2):  # SNS can deliver the same event twice
        proc.process(_wa_event(statuses=[delivered, read]))
    events = [e["type"] for e in svc.store.events_for(1) if e["message_id"] == message["id"]]
    assert events.count("delivered") == 1 and events.count("read") == 1


def test_receipt_for_unknown_message_is_ignored(svc):
    counts = AwsEventProcessor(svc).process(_wa_event(statuses=[{"id": "wamid.nope", "status": "read"}]))
    assert counts["receipts"] == 0 and counts["ignored"] == 1


def test_inbound_whatsapp_text_reaches_the_agent_once(svc):
    _opening(svc)
    proc = AwsEventProcessor(svc)
    inbound = {"from": _phone(svc), "id": "wamid.IN1", "type": "text", "text": {"body": "Can I pay quarterly?"}}
    assert proc.process(_wa_event(messages=[inbound]))["inbound"] == 1
    assert proc.process(_wa_event(messages=[inbound]))["inbound"] == 0  # duplicate delivery
    thread = svc.store.thread_for(1)
    bodies = [m["body"] for m in svc.store.thread_messages(thread["id"])]
    assert bodies.count("Can I pay quarterly?") == 1
    assert "quarterly" in bodies[-1].lower()  # the agent answered


def test_stop_over_whatsapp_opts_the_customer_out(svc):
    _opening(svc)
    stop = {"from": _phone(svc), "id": "wamid.IN2", "type": "text", "text": {"body": "STOP"}}
    AwsEventProcessor(svc).process(_wa_event(messages=[stop]))
    assert not any(svc.store.consents(1).values())


def test_non_text_and_unknown_senders_are_handled_safely(svc):
    _opening(svc)
    proc = AwsEventProcessor(svc)
    image = {"from": _phone(svc), "id": "wamid.IN3", "type": "image", "image": {"id": "x"}}
    assert proc.process(_wa_event(messages=[image]))["inbound"] == 1
    stranger = {"from": "919000000000", "id": "wamid.IN4", "type": "text", "text": {"body": "hi"}}
    assert proc.process(_wa_event(messages=[stranger]))["ignored"] == 1


def test_ses_bounce_revokes_email_consent(svc):
    svc.start_renewal(1)
    svc.inbound(1, "whatsapp", "Please email me the details")
    email = next(m for m in svc.store.thread_messages(svc.store.thread_for(1)["id"]) if m["channel"] == "email")
    mail = {"messageId": email["meta"]["provider_id"]}
    proc = AwsEventProcessor(svc)
    assert proc.process({"eventType": "Delivery", "mail": mail})["receipts"] == 1
    assert svc.store.has_event(email["id"], "delivered")
    proc.process({"eventType": "Bounce", "bounce": {"bounceType": "Permanent"}, "mail": mail})
    assert svc.store.consents(1)["email"] is False
    assert svc.store.consents(1)["whatsapp"] is True


def _client(svc):
    svc.settings = dataclasses.replace(svc.settings, webhook_token="secret", sns_verify=False, sns_topic_arns=("arn:aws:sns:us-east-1:1:t",))
    return TestClient(create_app(svc))


def _envelope(message, kind="Notification", topic="arn:aws:sns:us-east-1:1:t"):
    return json.dumps({"Type": kind, "TopicArn": topic, "Message": json.dumps(message)})


def test_webhook_rejects_wrong_token_and_wrong_topic(svc):
    client = _client(svc)
    body = _envelope({})
    assert client.post("/webhooks/sns/wrong", content=body).status_code == 404
    assert client.post("/webhooks/sns/secret", content=_envelope({}, topic="arn:other")).status_code == 403
    assert client.post("/webhooks/sns/secret", content="not json").status_code == 400


def test_webhook_processes_a_notification_end_to_end(svc):
    client = _client(svc)
    svc.start_renewal(1)
    inbound = {"from": _phone(svc), "id": "wamid.IN9", "type": "text", "text": {"body": "Why has my premium gone up?"}}
    res = client.post("/webhooks/sns/secret", content=_envelope(_wa_event(messages=[inbound])))
    assert res.status_code == 200 and res.json()["inbound"] == 1


def test_subscription_confirmation_only_follows_sns_urls(svc):
    client = _client(svc)
    evil = json.dumps({"Type": "SubscriptionConfirmation", "TopicArn": "arn:aws:sns:us-east-1:1:t", "SubscribeURL": "https://evil.example.com/x"})
    assert client.post("/webhooks/sns/secret", content=evil).status_code == 400
