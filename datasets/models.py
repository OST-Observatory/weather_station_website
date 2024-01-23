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

    #   Humidity in g/m3
    humidity = models.FloatField(default=0.)

    #   Illuminance in lx
    illuminance = models.FloatField(default=0.)

    #   Wind velocity in m/s
    wind_speed = models.FloatField(default=0.)

    #   Rain - uncalibrated value
    rain = models.FloatField(default=0. )

    #   Note
    note = models.TextField(default='')

    #   Bookkeeping
    added_on = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
