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


class CalibrationEpoch(models.Model):
    """
        Start of a sensor/hardware configuration. Cloud detection only calibrates
        with data from the latest epoch, so add one after every change at the
        sky sensors (window, mounting, sensor swap, firmware affecting them).
    """
    start = models.DateTimeField(unique=True)
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start']

    def __str__(self):
        return f'{self.start:%Y-%m-%d %H:%M} {self.note}'.strip()


class CloudBin(models.Model):
    """
        10-min aggregate of the sky sensors with the cloud detection result
        (see datasets/cloud_detection.py and the update_cloud_status command)
    """
    PERIOD_CHOICES = [('night', 'Night'), ('day', 'Day'), ('twilight', 'Twilight')]
    LABEL_CHOICES = [
        ('clear', 'Clear'),
        ('partly', 'Partly cloudy'),
        ('cloudy', 'Cloudy'),
        ('calibrating', 'Calibrating'),
        ('unknown', 'Unknown'),
    ]

    #   End of the 10-min bin (UTC)
    time = models.DateTimeField(unique=True)
    jd = models.FloatField()
    n_samples = models.IntegerField(default=0)
    sun_el = models.FloatField()
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES)

    #   Features (NaN/missing -> NULL)
    ir = models.FloatField(null=True, blank=True)
    lux = models.FloatField(null=True, blank=True)
    box = models.FloatField(null=True, blank=True)
    uv = models.FloatField(null=True, blank=True)

    #   Result: score 0 (clear) .. 1 (overcast)
    score = models.FloatField(null=True, blank=True)
    score_raw = models.FloatField(null=True, blank=True)
    label = models.CharField(max_length=12, choices=LABEL_CHOICES, default='unknown')
    #   Nights/days available for calibration when the bin was classified
    calibration_periods = models.IntegerField(default=0)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['time']

    def __str__(self):
        return f'{self.time:%Y-%m-%d %H:%M} {self.label}'


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
