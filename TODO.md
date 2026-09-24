# TODO

## Data protection / retention

The central privacy policy (`/static/datenschutz.html#en-weather-station` on
the landing site) promises limited storage. The following is not enforced yet:

- **django-axes records are never deleted.** `AccessLog` stores IP address,
  user agent and username of every admin login indefinitely. `AccessAttempt`
  (failed logins) is only purged after `AXES_COOLOFF_TIME` when the next login
  attempt happens, so the last entries can stay for a long time. Either
  schedule `python manage.py axes_reset_logs --age <days>` (cron or systemd
  timer; removes `AccessLog` rows older than `<days>`), or set
  `AXES_DISABLE_ACCESS_LOG = True` if successful logins need not be kept.
  For leftover `AccessAttempt` rows, a periodic `axes_reset` is fine (it only
  lifts lockouts). Update the policy with the chosen period.
- **Expired sessions are never cleared.** Schedule
  `python manage.py clearsessions` (daily).
- **Journald retention for the Gunicorn access log.** Gunicorn writes the
  access log (client IP, URL, user agent) to journald
  (`--access-logfile -` in `deploy/systemd/gunicorn_weather_station.service.example`).
  The policy says 7 days: set `MaxRetentionSec=7day` in `journald.conf` (or a
  drop-in) on the server, or check what the host already uses.
- **CSRF cookie for every dashboard visitor.** The two CSV download forms in
  `templates/datasets/dashboard.html` (~108 and ~123) use `method="get"` but
  contain `{% csrf_token %}`, so every visitor gets the `ost_weather_csrftoken`
  cookie. GET forms need no token (`site_static/js/dashboard.js` already drops
  `csrfmiddlewaretoken` before the request). Removing both tags means public
  visitors get no cookie at all; then the policy section can say so.
- **Development `debug.log` grows without limit.** `settings_development.py`
  uses a plain `FileHandler` at level DEBUG. Switch to
  `RotatingFileHandler`/`TimedRotatingFileHandler` with a small backup count,
  or log to the console in development.
