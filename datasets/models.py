from django.conf import settings
from django.db import models


class Dataset(models.Model):
    """
        Dataset class that deals with all the data submitted from the
        weather station to the database
    """
    #   Julian date the dataset was taken
    jd = models.FloatField(default=0.)

    # Provenance for HMAC uploads (null for historical / Basic-auth rows)
    upload_device = models.ForeignKey(
        'UploadDevice',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='datasets',
    )

    #   Temperature in °C
    temperature = models.FloatField(default=0.)

    #   Pressure in hPa
    pressure = models.FloatField(default=0.)

    #   Humidity in percent [%]
    humidity = models.FloatField(default=0.)

    #   Illuminance in lx
    illuminance = models.FloatField(default=0.)

    #   Anemometer revolutions per sample (display: × WIND_ROTATIONS_TO_MPS → m/s)
    wind_speed = models.FloatField(default=0.)

    #   Sky temperature in °C
    sky_temp = models.FloatField(default=0.)

    #   Box temperature (inside weather station box) in °C
    box_temp = models.FloatField(default=0.)

    #   Rain collector depth in mm (1.25 mm per gauge tip × tip count per sample).
    #   Dashboard plots convert to mm/m² via RAIN_TO_MM_PER_M2_FACTOR in plots.py.
    rain = models.FloatField(default=0. )

    #   Rain drop sensor flag (1: raining, 0: not raining)
    is_raining = models.IntegerField(default=0)

    #   PM1.0 concentration in ug/m3 (PMSA003I)
    pm1_0 = models.IntegerField(default=0)

    #   PM2.5 concentration in ug/m3 (PMSA003I)
    pm2_5 = models.IntegerField(default=0)

    #   PM10 concentration in ug/m3 (PMSA003I)
    pm10 = models.IntegerField(default=0)

    #   UV index (0-11+, WHO scale) from SEN0636
    uv_index = models.IntegerField(default=0)

    #   Note
    note = models.TextField(default='')

    #   Merged data?
    merged = models.BooleanField(default=False)

    #   Bookkeeping
    added_on = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['jd']),
            models.Index(fields=['added_on']),
            models.Index(fields=['merged', 'jd']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(humidity__gte=0.0) & models.Q(humidity__lte=100.0), name='humidity_0_100'),
            models.CheckConstraint(condition=models.Q(rain__gte=0.0), name='rain_non_negative'),
            models.CheckConstraint(condition=models.Q(is_raining__in=[0,1]), name='is_raining_bool'),
            models.CheckConstraint(condition=models.Q(pressure__gte=800.0) & models.Q(pressure__lte=1200.0), name='pressure_reasonable'),
            # Broad sanity bound — API enforces a tighter receive-time window.
            models.CheckConstraint(
                condition=models.Q(jd__gte=2400000.0) & models.Q(jd__lte=2600000.0),
                name='jd_broad_plausible',
            ),
        ]


class UploadDevice(models.Model):
    """Stable identity for a physical upload client (R4, legacy PC, …)."""

    device_id = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128, blank=True, default='')
    is_active = models.BooleanField(default=True)
    service_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='upload_device',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.device_id


class UploadSigningKey(models.Model):
    """Rotatable HMAC signing key; secret stored encrypted at rest."""

    device = models.ForeignKey(
        UploadDevice,
        on_delete=models.CASCADE,
        related_name='signing_keys',
    )
    key_id = models.CharField(max_length=64, unique=True)
    encrypted_secret = models.BinaryField()
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['device', 'key_id']),
        ]

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    def __str__(self):
        return self.key_id
