from django.core.management.base import BaseCommand

from datasets import cloud_status


class Command(BaseCommand):
    help = (
        'Aggregate new sky-sensor data into 10-min cloud bins and classify them '
        '(clear / partly / cloudy). Run every 10 minutes from cron. The first run '
        'backfills --backfill-days of history for the self-calibration.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--backfill-days', type=float, default=30.0,
            help='History to aggregate when no cloud bins exist yet (default: 30).',
        )
        parser.add_argument(
            '--recompute-days', type=float, default=0.0,
            help='Also re-classify stored bins of the last N days, e.g. after adding a '
                 'calibration epoch or changing CLOUD_DETECTION settings.',
        )

    def handle(self, *args, **options):
        new, classified = cloud_status.update(
            backfill_days=options['backfill_days'],
            recompute_days=options['recompute_days'],
        )
        status = cloud_status.current_status()
        current = status['text'] if status else 'no recent data'
        self.stdout.write(self.style.SUCCESS(
            f'{new} new cloud bin(s), {classified} classified; current: {current}.'
        ))
