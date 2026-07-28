"""Shared WEATHER-HMAC-V1 client helper for scripts and tests."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Mapping, MutableMapping, Optional, Tuple
from urllib.parse import urlencode


PROTOCOL = 'WEATHER-HMAC-V1'
DEFAULT_PATH = '/weather_station/weather_api/datasets/'
CONTENT_TYPE = 'application/x-www-form-urlencoded'


def body_sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def build_canonical(
    *,
    device_id: str,
    key_id: str,
    timestamp: str,
    nonce: str,
    body: bytes,
    path: str = DEFAULT_PATH,
    method: str = 'POST',
    content_type: str = CONTENT_TYPE,
) -> str:
    return '\n'.join([
        PROTOCOL,
        method,
        path,
        content_type,
        device_id,
        key_id,
        timestamp,
        nonce,
        body_sha256_hex(body),
    ])


def sign_body(
    secret: bytes,
    *,
    device_id: str,
    key_id: str,
    body: bytes,
    timestamp: Optional[str] = None,
    nonce: Optional[str] = None,
    path: str = DEFAULT_PATH,
) -> Tuple[bytes, MutableMapping[str, str]]:
    ts = timestamp if timestamp is not None else str(int(time.time()))
    nonce_hex = nonce if nonce is not None else secrets.token_hex(16)
    canonical = build_canonical(
        device_id=device_id,
        key_id=key_id,
        timestamp=ts,
        nonce=nonce_hex,
        body=body,
        path=path,
    )
    signature = hmac.new(secret, canonical.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {
        'Content-Type': CONTENT_TYPE,
        'X-Weather-Device': device_id,
        'X-Weather-Key-Id': key_id,
        'X-Weather-Timestamp': ts,
        'X-Weather-Nonce': nonce_hex,
        'X-Weather-Signature': signature,
    }
    return body, headers


def encode_form(data: Mapping) -> bytes:
    # doseq=False; preserve caller key order (Py3.7+ dict order).
    return urlencode(list(data.items()), doseq=False).encode('utf-8')


def parse_secret_hex(secret_hex: str) -> bytes:
    cleaned = (secret_hex or '').strip().replace('\r', '').replace('\n', '')
    if len(cleaned) != 64:
        raise ValueError('HMAC secret must be 64 hex characters (32 bytes)')
    return bytes.fromhex(cleaned)
