# Generated manually for HMAC upload devices and jd constraint.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def assert_jd_values_plausible(apps, schema_editor):
    Dataset = apps.get_model('datasets', 'Dataset')
    bad_count = Dataset.objects.filter(Q(jd__lt=2400000.0) | Q(jd__gt=2600000.0)).count()
    if bad_count:
        raise RuntimeError(
            f'{bad_count} Dataset row(s) have jd outside [2400000, 2600000]. '
            'Clean or correct them before applying jd_broad_plausible.'
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('datasets', '0006_dataset_uv_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='UploadDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_id', models.SlugField(max_length=64, unique=True)),
                ('label', models.CharField(blank=True, default='', max_length=128)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('service_user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='upload_device', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='UploadSigningKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key_id', models.CharField(max_length=64, unique=True)),
                ('encrypted_secret', models.BinaryField()),
                ('valid_from', models.DateTimeField()),
                ('valid_until', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='signing_keys', to='datasets.uploaddevice')),
            ],
        ),
        migrations.AddField(
            model_name='dataset',
            name='upload_device',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='datasets', to='datasets.uploaddevice'),
        ),
        migrations.AddIndex(
            model_name='uploadsigningkey',
            index=models.Index(fields=['device', 'key_id'], name='datasets_up_device__6f0f8e_idx'),
        ),
        migrations.RunPython(assert_jd_values_plausible, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='dataset',
            constraint=models.CheckConstraint(
                condition=models.Q(('jd__gte', 2400000.0), ('jd__lte', 2600000.0)),
                name='jd_broad_plausible',
            ),
        ),
    ]
