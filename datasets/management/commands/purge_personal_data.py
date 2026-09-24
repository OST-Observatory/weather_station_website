from importlib import import_module

from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_cool_off
from axes.models import AccessAttempt
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        'Delete personal data the privacy policy does not allow to keep: expired sessions, '
        'admin login logs older than AXES_ACCESS_LOG_RETENTION_DAYS and failed-login records '
        'whose lockout has expired. Run daily from cron.'
    )

    def handle(self, *args, **options):
        engine = import_module(settings.SESSION_ENGINE)
        engine.SessionStore.clear_expired()

        # AccessLog and AccessFailureLog (only filled if enabled) older than the retention period.
        age_days = settings.AXES_ACCESS_LOG_RETENTION_DAYS
        logs = AxesProxyHandler.reset_logs(age_days=age_days)
        logs += AxesProxyHandler.reset_failure_logs(age_days=age_days)

        # Unlike `axes_reset`, this keeps lockouts that are still active.
        attempts = 0
        cool_off = get_cool_off()
        if cool_off:
            attempts, _ = AccessAttempt.objects.filter(
                attempt_time__lt=timezone.now() - cool_off,
            ).delete()

        self.stdout.write(self.style.SUCCESS(
            f'Expired sessions cleared; {logs} access log(s) and {attempts} expired '
            f'failed-login record(s) removed.'
        ))
