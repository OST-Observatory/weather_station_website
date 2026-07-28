from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from datasets.credentials import encrypt_secret, generate_hmac_secret
from datasets.models import UploadDevice, UploadSigningKey
import secrets


class Command(BaseCommand):
    help = (
        'Provision an UploadDevice and initial HMAC signing key. '
        'Prints the plaintext secret once; it is never stored in cleartext.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--device-id', required=True, help='Stable device slug, e.g. r4-main')
        parser.add_argument('--label', default='', help='Human-readable label')
        parser.add_argument(
            '--username',
            default='',
            help='Service username (default: upload_<device_id>)',
        )

    def handle(self, *args, **options):
        device_id = slugify(options['device_id']).replace('-', '_') or options['device_id']
        if UploadDevice.objects.filter(device_id=device_id).exists():
            raise CommandError(f'Device {device_id} already exists')

        User = get_user_model()
        username = options['username'] or f'upload_{device_id}'
        if User.objects.filter(username=username).exists():
            raise CommandError(f'User {username} already exists')

        user = User.objects.create_user(username=username, password=None)
        user.set_unusable_password()
        user.is_staff = False
        user.is_superuser = False
        user.save()

        device = UploadDevice.objects.create(
            device_id=device_id,
            label=options['label'] or device_id,
            service_user=user,
            is_active=True,
        )

        plaintext = generate_hmac_secret()
        key_id = secrets.token_hex(8)
        UploadSigningKey.objects.create(
            device=device,
            key_id=key_id,
            encrypted_secret=encrypt_secret(plaintext),
            valid_from=timezone.now(),
        )

        self.stdout.write(self.style.SUCCESS(f'Created device {device.device_id}'))
        self.stdout.write(f'device_id={device.device_id}')
        self.stdout.write(f'key_id={key_id}')
        self.stdout.write(f'secret_hex={plaintext.hex()}')
        self.stdout.write(self.style.WARNING(
            'Store the secret_hex securely now; it will not be shown again.'
        ))
