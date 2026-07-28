import secrets

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from datasets.credentials import encrypt_secret, generate_hmac_secret
from datasets.models import UploadDevice, UploadSigningKey


class Command(BaseCommand):
    help = 'Create a new overlapping HMAC key for a device and optionally revoke the previous one.'

    def add_arguments(self, parser):
        parser.add_argument('--device-id', required=True)
        parser.add_argument(
            '--revoke-key-id',
            default='',
            help='Optional previous key_id to revoke after issuing the new key',
        )

    def handle(self, *args, **options):
        try:
            device = UploadDevice.objects.get(device_id=options['device_id'])
        except UploadDevice.DoesNotExist as exc:
            raise CommandError('Unknown device') from exc

        plaintext = generate_hmac_secret()
        key_id = secrets.token_hex(8)
        UploadSigningKey.objects.create(
            device=device,
            key_id=key_id,
            encrypted_secret=encrypt_secret(plaintext),
            valid_from=timezone.now(),
        )

        revoke_id = options['revoke_key_id']
        if revoke_id:
            updated = UploadSigningKey.objects.filter(
                device=device,
                key_id=revoke_id,
                revoked_at__isnull=True,
            ).update(revoked_at=timezone.now(), valid_until=timezone.now())
            if not updated:
                self.stdout.write(self.style.WARNING(f'No active key {revoke_id} to revoke'))

        self.stdout.write(self.style.SUCCESS(f'Rotated key for {device.device_id}'))
        self.stdout.write(f'device_id={device.device_id}')
        self.stdout.write(f'key_id={key_id}')
        self.stdout.write(f'secret_hex={plaintext.hex()}')
        self.stdout.write(self.style.WARNING(
            'Store the secret_hex securely now; it will not be shown again.'
        ))
