from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from datasets.models import UploadDevice, UploadSigningKey


class Command(BaseCommand):
    help = 'Revoke an upload signing key or deactivate an entire device.'

    def add_arguments(self, parser):
        parser.add_argument('--device-id', required=True)
        parser.add_argument('--key-id', default='', help='Revoke one key; omit to deactivate device')
        parser.add_argument(
            '--deactivate-device',
            action='store_true',
            help='Mark the device inactive (blocks all keys)',
        )

    def handle(self, *args, **options):
        try:
            device = UploadDevice.objects.get(device_id=options['device_id'])
        except UploadDevice.DoesNotExist as exc:
            raise CommandError('Unknown device') from exc

        now = timezone.now()
        key_id = options['key_id']
        if key_id:
            updated = UploadSigningKey.objects.filter(
                device=device,
                key_id=key_id,
                revoked_at__isnull=True,
            ).update(revoked_at=now, valid_until=now)
            if not updated:
                raise CommandError('Key not found or already revoked')
            self.stdout.write(self.style.SUCCESS(f'Revoked key {key_id}'))
            return

        if options['deactivate_device']:
            device.is_active = False
            device.save(update_fields=['is_active', 'updated_at'])
            UploadSigningKey.objects.filter(
                device=device,
                revoked_at__isnull=True,
            ).update(revoked_at=now, valid_until=now)
            self.stdout.write(self.style.SUCCESS(f'Deactivated device {device.device_id}'))
            return

        raise CommandError('Provide --key-id or --deactivate-device')
