"""SNS signature verification, locked admin endpoints, and the real Bedrock path with a fake client."""

from __future__ import annotations

import base64
import dataclasses
import json
from datetime import UTC, datetime, timedelta

import pytest
from conftest import outbound
from fastapi.testclient import TestClient

from renewflow.api.app import create_app
from renewflow.aws import sns_signature
from renewflow.llm.bedrock import BedrockModel

crypto = pytest.importorskip("cryptography")
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

CERT_URL = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(1).not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256())
    )
    return key, cert.public_bytes(serialization.Encoding.PEM)


def _signed(key, version="2", **over):
    env = {"Type": "Notification", "MessageId": "m1", "TopicArn": "arn:aws:sns:us-east-1:1:t",
           "Message": "{}", "Timestamp": "2026-10-27T00:00:00Z", "SignatureVersion": version,
           "SigningCertURL": CERT_URL, **over}
    digest = hashes.SHA256() if version == "2" else hashes.SHA1()
    sig = key.sign(sns_signature.string_to_sign(env).encode(), padding.PKCS1v15(), digest)
    env["Signature"] = base64.b64encode(sig).decode()
    return env


def test_valid_signatures_pass_for_both_versions(keypair):
    key, pem = keypair
    for version in ("1", "2"):
        assert sns_signature.verify(_signed(key, version), fetch=lambda _u: pem)


def test_tampered_or_untrusted_messages_fail(keypair):
    key, pem = keypair
    good = _signed(key)
    assert not sns_signature.verify({**good, "Message": '{"x":1}'}, fetch=lambda _u: pem)
    evil = _signed(key, SigningCertURL="https://evil.example.com/cert.pem")
    assert not sns_signature.verify(evil, fetch=lambda _u: pem)
    assert not sns_signature.verify({**good, "SigningCertURL": "http://sns.us-east-1.amazonaws.com/c.pem"},
                                    fetch=lambda _u: pem)
    assert not sns_signature.verify({**good, "Signature": "AAAA"}, fetch=lambda _u: pem)
    assert not sns_signature.verify({"Type": "Notification"})


def test_webhook_rejects_unsigned_messages_by_default(svc):
    svc.settings = dataclasses.replace(svc.settings, webhook_token="secret")
    client = TestClient(create_app(svc))
    body = json.dumps({"Type": "Notification", "Message": "{}"})
    assert client.post("/webhooks/sns/secret", content=body).status_code == 403


def test_admin_endpoints_are_locked_in_aws_mode(svc):
    svc.settings = dataclasses.replace(svc.settings, mode="aws", admin_token="")
    client = TestClient(create_app(svc))
    assert client.post("/api/reset").status_code == 403           # disabled without a token
    svc.settings = dataclasses.replace(svc.settings, admin_token="s3cret")
    assert client.post("/api/reset").status_code == 403           # wrong or missing token
    assert client.post("/api/reset", headers={"X-Admin-Token": "s3cret"}).status_code == 200
    assert client.get("/api/meta").json()["admin_locked"] is True


def test_admin_endpoints_stay_open_locally(svc):
    assert TestClient(create_app(svc)).post("/api/reset").status_code == 200


class FakeBedrock:
    """Plays a scripted conversation in the exact shape of bedrock-runtime.converse responses."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"role": "assistant", "content": self.script.pop(0)}}}


def test_agent_runs_end_to_end_on_the_real_bedrock_adapter(svc):
    client = FakeBedrock([
        [{"toolUse": {"toolUseId": "t1", "name": "lookup_policy", "input": {}}}],
        [{"toolUse": {"toolUseId": "t2", "name": "send_message", "input": {
            "channel": "whatsapp", "kind": "info",
            "body": "Your renewal premium is ₹14,800, down from last year's ₹18,400."}}}],
        [{"text": "Answered the premium question."}],
    ])
    svc.model = BedrockModel(client, "test-model")
    svc.agent.model = svc.model
    first = svc.start_renewal(1)  # proactive opener through the same model
    sent = outbound(svc, first.thread_id)
    assert client.calls and all("toolConfig" in c for c in client.calls)
    assert client.calls[0]["messages"][0]["role"] == "user"
    assert first.outcome == "contacted" and len(client.calls) == 3
    assert any("₹14,800" in m["body"] for m in sent)


def test_invented_prices_from_a_real_model_are_blocked(svc):
    client = FakeBedrock([
        [{"toolUse": {"toolUseId": "t1", "name": "lookup_policy", "input": {}}}],
        [{"toolUse": {"toolUseId": "t2", "name": "send_message", "input": {
            "channel": "whatsapp", "kind": "info", "body": "Special offer: only ₹9,999 today!"}}}],
        [{"text": "done"}],
    ])
    svc.model = BedrockModel(client, "test-model")
    svc.agent.model = svc.model
    first = svc.start_renewal(1)
    assert not any("₹9,999" in m["body"] for m in outbound(svc, first.thread_id))
