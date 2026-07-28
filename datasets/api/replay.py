"""Redis/cache-backed nonce replay and idempotent upload retries."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.base import InvalidCacheBackendError

logger = logging.getLogger('weather.upload')


@dataclass
class ReplayReservation:
    key: str
    created: bool


def _cache():
    alias = getattr(settings, 'UPLOAD_REPLAY_CACHE_ALIAS', 'default')
    try:
        return caches[alias]
    except InvalidCacheBackendError:
        return caches['default']


def _ttl() -> int:
    return int(getattr(settings, 'UPLOAD_HMAC_REPLAY_TTL_SECONDS', 600))


def replay_key(device_id: str, key_id: str, nonce: str) -> str:
    return f'upload-hmac-v1:{device_id}:{key_id}:{nonce}'


def reserve_nonce(device_id: str, key_id: str, nonce: str, body_digest: str) -> ReplayReservation:
    """
    Atomically reserve a nonce.

    Returns created=True for a fresh reservation.
    Raises ReplayConflict for same nonce with different body.
    Raises ReplayStoreUnavailable if the cache backend fails.
    """
    cache = _cache()
    key = replay_key(device_id, key_id, nonce)
    payload = json.dumps({'state': 'pending', 'body_digest': body_digest})
    try:
        created = cache.add(key, payload, timeout=_ttl())
    except Exception as exc:
        logger.error('replay_store_unavailable op=add device=%s key_id=%s', device_id, key_id)
        raise ReplayStoreUnavailable from exc

    if created:
        return ReplayReservation(key=key, created=True)

    existing = _load(key)
    if existing is None:
        # Race: expired between add failure and get — try once more.
        try:
            created = cache.add(key, payload, timeout=_ttl())
        except Exception as exc:
            raise ReplayStoreUnavailable from exc
        if created:
            return ReplayReservation(key=key, created=True)
        existing = _load(key)

    if existing and existing.get('body_digest') != body_digest:
        raise ReplayConflict('nonce reused with different body')
    return ReplayReservation(key=key, created=False)


def mark_success(reservation: ReplayReservation, body_digest: str, response_pk: int) -> None:
    cache = _cache()
    payload = json.dumps({
        'state': 'success',
        'body_digest': body_digest,
        'pk': response_pk,
    })
    try:
        cache.set(reservation.key, payload, timeout=_ttl())
    except Exception as exc:
        raise ReplayStoreUnavailable from exc


def get_success(device_id: str, key_id: str, nonce: str, body_digest: str) -> Optional[int]:
    existing = _load(replay_key(device_id, key_id, nonce))
    if not existing:
        return None
    if existing.get('state') != 'success':
        return None
    if existing.get('body_digest') != body_digest:
        raise ReplayConflict('nonce reused with different body')
    pk = existing.get('pk')
    return int(pk) if pk is not None else None


def _load(key: str) -> Optional[dict]:
    cache = _cache()
    try:
        raw = cache.get(key)
    except Exception as exc:
        raise ReplayStoreUnavailable from exc
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


class ReplayConflict(Exception):
    pass


class ReplayStoreUnavailable(Exception):
    pass
