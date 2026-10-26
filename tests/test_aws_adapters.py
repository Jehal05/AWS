"""AWS adapters, checked against botocore's real request/response schemas with no network."""

import itertools
import json

import boto3
import pytest
from botocore.stub import Stubber

from renewflow.channels.aws import AwsWhatsAppChannel, SesEmailChannel
from renewflow.channels.base import OutboundMessage
from renewflow.llm.bedrock import BedrockModel, to_converse, to_tool_config


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")


def _client(service):
    return boto3.client(service, region_name="us-east-1")


def _message(svc, channel, kind="info", body="Hello there", subject=None):
    return OutboundMessage(svc.store.get_customer(1), channel, body, subject, {"kind": kind})


def test_whatsapp_text_message_uses_the_documented_payload(svc):
    client = _client("socialmessaging")
    channel = AwsWhatsAppChannel(client, "phone-number-id-abc", "v20.0")
    customer = svc.store.get_customer(1)
    expected = channel.payload(_message(svc, "whatsapp"))
    assert expected["to"] == customer.phone and expected["type"] == "text"
    assert expected["text"]["body"] == "Hello there"

    with Stubber(client) as stub:
        stub.add_response(
            "send_whatsapp_message",
            {"messageId": "wamid.123"},
            {
                "message": json.dumps(expected).encode(),
                "originationPhoneNumberId": "phone-number-id-abc",
                "metaApiVersion": "v20.0",
            },
        )
        result = channel.send(_message(svc, "whatsapp"))
    assert result.ok and result.provider_message_id == "wamid.123" and not result.delivered


def test_whatsapp_opening_message_uses_the_approved_template(svc):
    channel = AwsWhatsAppChannel(_client("socialmessaging"), "phone-number-id-abc", template="renewal_intro")
    body = "Line one\n\nLine   two"
    proactive = channel.payload(_message(svc, "whatsapp", kind="proactive", body=body))
    assert proactive["type"] == "template" and proactive["template"]["name"] == "renewal_intro"
    param = proactive["template"]["components"][0]["parameters"][0]["text"]
    assert param == "Line one Line two"  # WhatsApp rejects newlines inside template parameters
    reply = channel.payload(_message(svc, "whatsapp", kind="quote"))
    assert reply["type"] == "text"  # replies stay free-form inside the 24 hour window


def test_whatsapp_failure_becomes_a_result_not_an_exception(svc):
    client = _client("socialmessaging")
    channel = AwsWhatsAppChannel(client, "phone-number-id-abc")
    with Stubber(client) as stub:
        stub.add_client_error("send_whatsapp_message", "ThrottledRequestException", "slow down")
        result = channel.send(_message(svc, "whatsapp"))
    assert not result.ok and "ThrottledRequestException" in result.error


def test_whatsapp_requires_a_phone_number_id():
    with pytest.raises(ValueError):
        AwsWhatsAppChannel(object(), "")


def test_ses_send_email_request_and_result(svc):
    client = _client("sesv2")
    channel = SesEmailChannel(client, "renewals@example.com", "renewflow-events")
    message = _message(svc, "email", body="Plan: Quarterly", subject="Your renewal")
    with Stubber(client) as stub:
        stub.add_response("send_email", {"MessageId": "ses-1"}, channel.request(message))
        result = channel.send(message)
    assert result.ok and result.provider_message_id == "ses-1"
    req = channel.request(message)
    assert req["ConfigurationSetName"] == "renewflow-events"
    assert req["Content"]["Simple"]["Subject"]["Data"] == "Your renewal"


def test_ses_failure_is_reported(svc):
    client = _client("sesv2")
    channel = SesEmailChannel(client, "renewals@example.com")
    with Stubber(client) as stub:
        stub.add_client_error("send_email", "MessageRejected", "Email address is not verified")
        result = channel.send(_message(svc, "email"))
    assert not result.ok and "MessageRejected" in result.error


def test_converse_translation_keeps_roles_alternating_and_merges_tool_results():
    messages = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "assistant", "content": "[whatsapp] Hi Priya"},  # history starts with the assistant
        {"role": "user", "content": "[whatsapp] Why higher?"},
        {"role": "user", "content": "Customer replied"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "t1", "name": "lookup_policy", "arguments": {}},
                {"id": "t2", "name": "next_best_channel", "arguments": {}},
            ],
        },
        {"role": "tool", "name": "lookup_policy", "tool_call_id": "t1", "content": '{"ok": true}'},
        {"role": "tool", "name": "next_best_channel", "tool_call_id": "t2", "content": "[1, 2]"},
    ]
    converse, system = to_converse(messages)
    assert system == [{"text": "You are an assistant."}]
    roles = [m["role"] for m in converse]
    assert roles == ["user", "assistant", "user", "assistant", "user"]
    assert all(a != b for a, b in itertools.pairwise(roles))
    assert len(converse[2]["content"]) == 2  # consecutive user turns merged
    results = converse[-1]["content"]
    assert [r["toolResult"]["toolUseId"] for r in results] == ["t1", "t2"]
    assert results[1]["toolResult"]["content"][0]["json"] == {"result": [1, 2]}  # json must be an object


def test_bedrock_model_parses_tool_use_and_text():
    client = _client("bedrock-runtime")
    model = BedrockModel(client, "test-model")
    from renewflow.agent.tools import TOOL_SPECS

    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    converse, system = to_converse(messages)
    expected = {
        "modelId": "test-model",
        "messages": converse,
        "system": system,
        "toolConfig": to_tool_config(TOOL_SPECS),
        "inferenceConfig": {"maxTokens": 1024, "temperature": 0.2},
    }
    reply = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"text": "Checking."},
                    {"toolUse": {"toolUseId": "abc", "name": "lookup_policy", "input": {}}},
                ],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        "metrics": {"latencyMs": 5},
    }
    with Stubber(client) as stub:
        stub.add_response("converse", reply, expected)
        turn = model.respond(messages, TOOL_SPECS)
    assert turn.text == "Checking." and turn.tool_calls[0].name == "lookup_policy"
    assert turn.tool_calls[0].id == "abc" and model.name == "bedrock:test-model"


def test_aws_mode_mixes_live_and_simulated_channels(monkeypatch):
    import dataclasses

    from renewflow.channels.local import LocalChannel
    from renewflow.channels.registry import build_channels
    from renewflow.config import Settings

    base = Settings(mode="aws", enabled_channels=("whatsapp", "email"), local_channels=("whatsapp",))
    settings = dataclasses.replace(base, ses_from="renewals@example.com", aws_region="us-east-1")
    channels = build_channels(settings)
    assert isinstance(channels["whatsapp"], LocalChannel) and isinstance(channels["email"], SesEmailChannel)
    with pytest.raises(ValueError):  # a live WhatsApp channel without a phone number id must not start
        build_channels(dataclasses.replace(settings, local_channels=()))
