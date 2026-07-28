"""WEATHER-HMAC-V1 canonical string and signature helpers."""

from __future__ import annotations

import hashlib
import hmac
from typing import Union

BytesLike = Union[bytes, bytearray, memoryview]

PROTOCOL = 'WEATHER-HMAC-V1'
DEFAULT_METHOD = 'POST'
DEFAULT_CONTENT_TYPE = 'application/x-www-form-urlencoded'


def body_sha256_hex(body: BytesLike) -> str:
    return hashlib.sha256(bytes(body)).hexdigest()


def canonical_string(
    *,
    method: str,
    path: str,
    content_type: str,
    device_id: str,
    key_id: str,
    timestamp: str,
    nonce: str,
    body_digest_hex: str,
) -> str:
    """
    Canonical string, UTF-8, no trailing newline:

    WEATHER-HMAC-V1
    POST
    /weather_station/weather_api/datasets/
    application/x-www-form-urlencoded
    <device_id>
    <key_id>
    <timestamp>
    <nonce>
    <sha256_hex_of_exact_raw_body>
    """
    return '\n'.join([
        PROTOCOL,
        method,
        path,
        content_type,
        device_id,
        key_id,
        timestamp,
        nonce,
        body_digest_hex,
    ])


def sign_canonical(secret: bytes, canonical: str) -> str:
    digest = hmac.new(secret, canonical.encode('utf-8'), hashlib.sha256).hexdigest()
    return digest


def verify_signature(secret: bytes, canonical: str, signature_hex: str) -> bool:
    expected = sign_canonical(secret, canonical)
    provided = (signature_hex or '').strip().lower()
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(expected, provided)
