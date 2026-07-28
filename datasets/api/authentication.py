"""DRF authentication for WEATHER-HMAC-V1 and dual-mode legacy Basic Auth."""

from __future__ import annotations

import logging
import re
import time

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, BasicAuthentication

from datasets.credentials import decrypt_secret
from datasets.models import UploadDevice, UploadSigningKey

from . import signing

logger = logging.getLogger('weather.upload')

HEADER_DEVICE = 'HTTP_X_WEATHER_DEVICE'
HEADER_KEY_ID = 'HTTP_X_WEATHER_KEY_ID'
HEADER_TIMESTAMP = 'HTTP_X_WEATHER_TIMESTAMP'
HEADER_NONCE = 'HTTP_X_WEATHER_NONCE'
HEADER_SIGNATURE = 'HTTP_X_WEATHER_SIGNATURE'

_NONCE_RE = re.compile(r'^[0-9a-fA-F]{32}$')
_KEY_ID_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
_DEVICE_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')


class DeviceHMACAuthentication(BaseAuthentication):
    """Authenticate uploads via HMAC-SHA256 over the exact raw body."""

    www_authenticate_realm = 'weather-upload'

    def authenticate(self, request):
        device_id = request.META.get(HEADER_DEVICE)
        key_id = request.META.get(HEADER_KEY_ID)
        timestamp = request.META.get(HEADER_TIMESTAMP)
        nonce = request.META.get(HEADER_NONCE)
        signature = request.META.get(HEADER_SIGNATURE)

        header_present = any([device_id, key_id, timestamp, nonce, signature])
        if not header_present:
            return None
        if not all([device_id, key_id, timestamp, nonce, signature]):
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        if not _DEVICE_RE.match(device_id) or not _KEY_ID_RE.match(key_id):
            raise exceptions.AuthenticationFailed('Invalid upload credentials')
        if not _NONCE_RE.match(nonce):
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        skew = int(getattr(settings, 'UPLOAD_HMAC_TIMESTAMP_SKEW_SECONDS', 300))
        now = int(time.time())
        if abs(now - ts) > skew:
            logger.info('hmac_auth_failed reason=timestamp_skew device=%s key_id=%s', device_id, key_id)
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        try:
            device = UploadDevice.objects.select_related('service_user').get(device_id=device_id)
        except UploadDevice.DoesNotExist:
            logger.info('hmac_auth_failed reason=unknown_device device=%s', device_id)
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        if not device.is_active or not device.service_user.is_active:
            logger.info('hmac_auth_failed reason=inactive_device device=%s', device_id)
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        try:
            signing_key = UploadSigningKey.objects.get(device=device, key_id=key_id)
        except UploadSigningKey.DoesNotExist:
            logger.info('hmac_auth_failed reason=unknown_key device=%s key_id=%s', device_id, key_id)
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        now_dt = timezone.now()
        if signing_key.revoked_at is not None:
            raise exceptions.AuthenticationFailed('Invalid upload credentials')
        if signing_key.valid_from > now_dt:
            raise exceptions.AuthenticationFailed('Invalid upload credentials')
        if signing_key.valid_until is not None and signing_key.valid_until <= now_dt:
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        content_type = (request.META.get('CONTENT_TYPE') or '').split(';')[0].strip().lower()
        if content_type != signing.DEFAULT_CONTENT_TYPE:
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        body = request.body
        body_digest = signing.body_sha256_hex(body)
        path = getattr(settings, 'UPLOAD_HMAC_CANONICAL_PATH', '/weather_station/weather_api/datasets/')
        canonical = signing.canonical_string(
            method=signing.DEFAULT_METHOD,
            path=path,
            content_type=signing.DEFAULT_CONTENT_TYPE,
            device_id=device_id,
            key_id=key_id,
            timestamp=str(ts),
            nonce=nonce.lower(),
            body_digest_hex=body_digest,
        )
        secret = decrypt_secret(signing_key.encrypted_secret)
        if not signing.verify_signature(secret, canonical, signature):
            logger.info('hmac_auth_failed reason=bad_signature device=%s key_id=%s', device_id, key_id)
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        request.upload_device = device
        request.upload_signing_key = signing_key
        request.upload_hmac = {
            'device_id': device_id,
            'key_id': key_id,
            'timestamp': str(ts),
            'nonce': nonce.lower(),
            'body_digest': body_digest,
        }
        return (device.service_user, 'hmac-v1')

    def authenticate_header(self, request):
        return f'WeatherHMAC realm="{self.www_authenticate_realm}"'


class LegacyUploadBasicAuthentication(BasicAuthentication):
    """
    Basic Auth restricted to the dedicated legacy upload user.

    Used only while UPLOAD_AUTH_MODE=dual. Admins and arbitrary users are rejected.
    """

    def authenticate(self, request):
        mode = getattr(settings, 'UPLOAD_AUTH_MODE', 'hmac_only')
        if mode != 'dual':
            return None
        # Prefer HMAC when its headers are present.
        if request.META.get(HEADER_DEVICE) or request.META.get(HEADER_SIGNATURE):
            return None
        return super().authenticate(request)

    def authenticate_credentials(self, userid, password, request=None):
        legacy_username = getattr(settings, 'UPLOAD_LEGACY_BASIC_USERNAME', 'data_upload_user')
        if userid != legacy_username:
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        credentials = {get_user_model().USERNAME_FIELD: userid, 'password': password}
        user = authenticate(request=request, **credentials)
        if user is None or not user.is_active:
            raise exceptions.AuthenticationFailed('Invalid upload credentials')
        if user.is_staff or user.is_superuser:
            raise exceptions.AuthenticationFailed('Invalid upload credentials')

        logger.warning('legacy_basic_upload_auth user=%s', userid)
        if request is not None:
            request.upload_device = None
            request.upload_hmac = None
            request.legacy_basic_upload = True
        return (user, None)
