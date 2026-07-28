# HMAC cutover and canary checklist

Operational steps after code deploy. Do not put secrets in tickets.

## Pre-cutover

1. Provision devices: `provision_upload_device` for R4 and legacy Windows PC.
2. Flash R4 `secrets.h` / update Windows `weather_station_config.json` with device_id, key_id, secret_hex.
3. Set `UPLOAD_AUTH_MODE=dual` and restart Gunicorn.
4. Confirm Redis is up; HMAC uploads must fail closed (503) if replay store is down.

## Canary

1. Staging: one HMAC upload from Windows `receive.py`, then from R4.
2. Production canary: single device only; watch `weather.upload` logs (device/key id + error class only).
3. Verify: lost-response retry (same nonce/body → one DB row), replay with new body → reject, clock skew ±300 s, 429 backoff, key rotation.

## Cutover to hmac_only

After ≥7 consecutive days with no successful Basic uploads:

1. Set `UPLOAD_AUTH_MODE=hmac_only`.
2. Restart Gunicorn.
3. Disable legacy Basic password (`set_unusable_password` on `data_upload_user`).
4. Revoke unused keys; keep one active key per device.
5. Confirm Basic Auth → 401.

## Authorized retest

Within the agreed maintenance window, retest XSS payloads (text only), anonymous `fresh=1` (no force recompute), throttles (429), spoofed XFF (stable identity), and HMAC negative cases.
