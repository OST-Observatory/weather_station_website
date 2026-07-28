"""Encrypted-at-rest storage helpers for upload HMAC secrets."""

from __future__ import annotations

import secrets

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet() -> Fernet:
    key = getattr(settings, 'UPLOAD_CREDENTIAL_MASTER_KEY', None) or ''
    if not key:
        raise ImproperlyConfigured(
            'UPLOAD_CREDENTIAL_MASTER_KEY is required to encrypt upload signing secrets'
        )
    try:
        return Fernet(key.encode('ascii') if isinstance(key, str) else key)
    except Exception as exc:
        raise ImproperlyConfigured(
            'UPLOAD_CREDENTIAL_MASTER_KEY must be a valid Fernet key '
            '(generate with cryptography.fernet.Fernet.generate_key())'
        ) from exc


def generate_hmac_secret() -> bytes:
    return secrets.token_bytes(32)


def encrypt_secret(plaintext: bytes) -> bytes:
    return _fernet().encrypt(plaintext)


def decrypt_secret(ciphertext: bytes) -> bytes:
    try:
        return _fernet().decrypt(bytes(ciphertext))
    except InvalidToken as exc:
        raise ImproperlyConfigured('Failed to decrypt upload signing secret') from exc
