import os

from django.shortcuts import render
from django.db.models import Max

import datetime

import time

import astropy.coordinates as coord
from astropy.time import Time
import astropy.units as u

from astroplan import Observer

from .plots import default_plots

from .forms import ParameterPlotForm

from .models import Dataset


# Create your views here.


def dashboard(request, **kwargs):
    """
        Collect weather station data, plot those data, and render request
    """
    ###
    #   Prepare form
    #
    parameters = {}
    if request.method == 'GET':
        form = ParameterPlotForm(request.GET)
        if form.is_valid():
            parameters = form.cleaned_data
        else:
            form = ParameterPlotForm(
                initial={'time_resolution': 300, 'plot_range': 0.5}
            )
    else:
        form = ParameterPlotForm(
            initial={'time_resolution': 300, 'plot_range': 0.5}
        )

    ###
    #   Plots
    #
    #   Create HTML content for default plots
    script, div = default_plots(**parameters)

    ###
    #   Sunrise and sunset
    #

    #   Location
    location = coord.EarthLocation(lat=+52.409184, lon=+12.973185, height=39)

    #   Define the location by means of astroplan
    ost = Observer(location=location, name="OST", timezone="Europe/Berlin")

    #   Current time
    current_time = Time.now()

    #   Sunset
    sunset_tonight = ost.sun_set_time(
        current_time,
        horizon=-0.8333 * u.deg,
        which='nearest',
    )

    #   Sunrise
    sunrise_tonight = ost.sun_rise_time(
        current_time,
        horizon=-0.8333 * u.deg,
        which='nearest',
    )

    #   Prepare strings for sunrise and sunset output
    os.environ['TZ'] = 'Europe/Berlin'
    time.tzset()
    timezone_hour_delta = time.timezone / 3600 * -1
    delta = datetime.timedelta(hours=timezone_hour_delta)
    sunrise_local = sunrise_tonight.datetime + delta
    sunset_local = sunset_tonight.datetime + delta
    sunrise_output_format = f'{sunrise_local.hour:02d}:{sunrise_local.minute:02d}'
    sunset_output_format = f'{sunset_local.hour:02d}:{sunset_local.minute:02d}'

    ###
    #   Current/Latest data in the database
    #
    added_on__max = Dataset.objects.all().aggregate(
        Max('added_on')
    )['added_on__max']

    try:
        latest_data = Dataset.objects.get(added_on=added_on__max)

        temperature = f'{latest_data.temperature:.0f}'
        pressure = f'{latest_data.pressure:.0f}'
        humidity = f'{latest_data.humidity:.0f}'
        illuminance = f'{latest_data.illuminance:.0f}'
        wind_speed = f'{latest_data.wind_speed:.0f}'
    except:
        temperature, pressure, humidity, illuminance = '0', '0', '0', '0'
        wind_speed = '0'

    #   Setup date string from local time
    timezone_info = datetime.timezone(
        datetime.timedelta(hours=timezone_hour_delta)
    )
    local_time = datetime.datetime.now(timezone_info)
    weak_days = {
        1: 'Monday',
        2: 'Tuesday',
        3: 'Wednesday',
        4: 'Thursday',
        5: 'Friday',
        6: 'Saturday',
        7: 'Sunday',
    }
    months = {
        1: 'January',
        2: 'February',
        3: 'March',
        4: 'April',
        5: 'May',
        6: 'June',
        7: 'July',
        8: 'August',
        9: 'September',
        10: 'October',
        11: 'November',
        12: 'December',
    }
    weak_day = weak_days[local_time.isoweekday()]
    month = months[local_time.month]
    day = local_time.day
    date_str = f'{weak_day}, {month} {day}'

    ###
    #   Weather symbol
    #
    if datetime.datetime.now().timestamp() > sunset_tonight.datetime.timestamp():
        symbol = 'night'
    else:
        symbol = 'day'

    #   Make dict with the content
    context = {
        'figures': div,
        'script': script,
        'sunset': sunset_output_format,
        'sunrise': sunrise_output_format,
        'temperature': temperature,
        'pressure': pressure,
        'humidity': humidity,
        'illuminance': illuminance,
        'wind_speed': wind_speed,
        'date_str': date_str,
        'symbol': symbol,
        'form': form
    }

    return render(request, 'datasets/dashboard.html', context)
