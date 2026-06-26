from django.db import models

# Create your models here.


class Dataset(models.Model):
    """
        Dataset class that deals with all the data submitted from the
        weather station to the database
    """
    #   Julian date the dataset was taken
    jd = models.FloatField(default=0.)

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
        ]
