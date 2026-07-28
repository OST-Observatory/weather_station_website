# Security operations runbook

Operational checklist for the OST weather station website. Do not paste production secrets into tickets, chat, or logs.

## Day-0 inventory (production host)

1. Confirm a current PostgreSQL dump and a copy of the live `.env` are available in a restricted backup location.
2. Inventory Apache vhosts, TLS certificates, systemd units (`gunicorn_weather_station.*`), Redis status, and active upload clients (UNO R4 WiFi firmware and legacy Windows `receive.py`).
3. Record a rollback artifact (DB dump + previous static/code tree) and a maintenance window before credential or auth-mode changes.

## Secret file permissions

On the production host (not in Git):

```bash
# Example paths — adjust to the real deploy tree
sudo chown weather_station_user:weather_station_user /path/to/weather_station/.env
sudo chmod 600 /path/to/weather_station/.env
sudo chmod 700 /path/to/weather_station   # or 750 if www-data must traverse
```

Verify with `namei -l` / `ls -la` that world/group cannot read secrets. Never commit real `.env` files.

## Credential rotation

Rotate when the host is multi-user, backups were world-readable, or secrets may have leaked:

| Secret | Effect |
|--------|--------|
| `SECRET_KEY` | Invalidates Django sessions; does not delete weather data |
| Database password | Update `.env` and Postgres role together; restart Gunicorn |
| Legacy Basic upload password | Coordinate with HMAC cutover; prefer migrating clients first |
| `UPLOAD_CREDENTIAL_MASTER_KEY` | Requires re-encrypting all `UploadSigningKey` secrets before rotation |
| Device HMAC secrets | Use `manage.py rotate_upload_key`; flash/update clients; revoke old key |

## Production mode verification

```bash
# On the app host, as the service user
grep -E '^DJANGO_ENV=' weather_station/.env   # must be production
python manage.py shell -c "from django.conf import settings; print(settings.DEBUG, settings.DJANGO_ENV)"
python manage.py check --deploy
```

Confirm HTTP redirects to HTTPS at the Apache edge and that `/admin/` is not reachable from the public Internet.

## Go-live checklist

- [ ] `DJANGO_ENV=production`, `DEBUG=False`
- [ ] Redis reachable (`REDIS_URL`), authenticated, bound to loopback/Unix socket
- [ ] `.env` mode `600`, owned by Gunicorn user
- [ ] `UPLOAD_AUTH_MODE` set (`dual` during migration, then `hmac_only`)
- [ ] `UPLOAD_CREDENTIAL_MASTER_KEY` set (Fernet key, independent of `SECRET_KEY`)
- [ ] Apache templates from `deploy/apache/` applied (HTTPS redirect, X-Forwarded-*, Admin IP allowlist)
- [ ] `collectstatic` run after static changes
- [ ] `pip install --require-hashes -r requirements.txt`
- [ ] Upload canary from R4 and Windows legacy client succeeded

## Logging hygiene

Never log Authorization headers, HMAC signatures, nonces, secrets, or full upload payloads. Prefer device id, key id, and error class only.

## Incident notes

After any suspected compromise: rotate upload keys and Basic password (if still enabled), rotate `SECRET_KEY` if session forgery is possible, review Apache/Gunicorn logs for anomalous upload volume, and restore from the Day-0 dump if data integrity is uncertain.
