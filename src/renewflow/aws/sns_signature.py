"""Verify the signature on an Amazon SNS HTTP message.

Follows the documented procedure: the signing certificate must come from an SNS host over https,
the string to sign is built from a fixed, ordered list of fields, and the signature is checked
with the certificate's RSA key (SHA1 for SignatureVersion 1, SHA256 for version 2).
"""

from __future__ import annotations

import base64
import re
import urllib.request
from collections.abc import Callable
from functools import lru_cache
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

CERT_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$")
_FIELDS = {
    "Notification": ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"],
    "SubscriptionConfirmation": [
        "Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type",
    ],
}
_FIELDS["UnsubscribeConfirmation"] = _FIELDS["SubscriptionConfirmation"]


def string_to_sign(envelope: dict) -> str:
    names = _FIELDS.get(envelope.get("Type", ""))
    if names is None:
        raise ValueError("unsupported message type")
    return "".join(f"{n}\n{envelope[n]}\n" for n in names if n in envelope)


@lru_cache(maxsize=8)
def _fetch_cert(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as res:
        return res.read()


def verify(envelope: dict, fetch: Callable[[str], bytes] | None = None) -> bool:
    """True only if the message is correctly signed by an SNS certificate."""
    try:
        url = urlparse(envelope.get("SigningCertURL", ""))
        if url.scheme != "https" or not CERT_HOST.match(url.hostname or ""):
            return False
        version = str(envelope.get("SignatureVersion", ""))
        digest = {"1": hashes.SHA1(), "2": hashes.SHA256()}.get(version)
        if digest is None:
            return False
        cert = x509.load_pem_x509_certificate((fetch or _fetch_cert)(url.geturl()))
        cert.public_key().verify(
            base64.b64decode(envelope["Signature"]),
            string_to_sign(envelope).encode(),
            padding.PKCS1v15(),
            digest,
        )
        return True
    except Exception:  # noqa: BLE001 - any parse, network or crypto failure means "not verified"
        return False
