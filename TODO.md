# TODO

## Done

### Data protection / retention (2026-09)

The central privacy policy (`/static/datenschutz.html#en-weather-station` on the landing
site) states what is stored and for how long; README → *Data protection / retention*.

- [x] django-axes: admin login logs (`AccessLog`, `AccessFailureLog`) deleted after 30 days
  (`AXES_ACCESS_LOG_RETENTION_DAYS`), expired failed-login records removed while active
  lockouts stay — `manage.py purge_personal_data`, daily cron
- [x] Expired sessions cleared by the same command
- [x] Journald keeps 7 days on the server (documented in README)
- [x] No CSRF cookie for dashboard visitors: `{% csrf_token %}` removed from the two GET
  download forms; test `test_dashboard_sets_no_cookies`
- [x] Development `debug.log` rotates (`RotatingFileHandler`, 10 MB × 3)
