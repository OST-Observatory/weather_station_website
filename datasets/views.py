import os
import csv
from django.http import HttpResponse

from django.shortcuts import render
from django.db.models import Max

import datetime

import time

import numpy as np

import astropy.coordinates as coord
from astropy.time import Time
import astropy.units as u

from astroplan import Observer

from .plots import default_plots

from .forms import ParameterPlotForm, DateRangeForm

from .models import Dataset

from datetime import datetime, timedelta, timezone
import pytz


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
        date_form = DateRangeForm(request.GET)
        if form.is_valid():
            parameters = form.cleaned_data
        else:
            form = ParameterPlotForm(
                initial={'time_resolution': 300, 'plot_range': 0.5}
            )
            date_form = DateRangeForm()
    else:
        form = ParameterPlotForm(
            initial={'time_resolution': 300, 'plot_range': 0.5}
        )
        date_form = DateRangeForm()

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
    delta = timedelta(hours=timezone_hour_delta)
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
        # wind_gust = f'{latest_data.wind_speed:.0f}'

        wind_gust_two_minutes = Dataset.objects.filter(
            jd__range=[latest_data.jd-0.001388889, latest_data.jd]
        ).values_list("wind_speed")
        wind_speed = np.mean(wind_gust_two_minutes)
        #   Convert wind speed from rotation to m/s
        wind_speed = f'{wind_speed * 1.4:.0f}'

    except:
        temperature, pressure, humidity, illuminance = '0', '0', '0', '0'
        wind_speed = '0'

    #   Setup date string from local time
    timezone_info = timezone(
        timedelta(hours=timezone_hour_delta)
    )
    local_time = datetime.now(timezone_info)
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
    if datetime.now().timestamp() > sunset_tonight.datetime.timestamp():
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
        'form': form,
        'date_form': date_form
    }

    return render(request, 'datasets/dashboard.html', context)

def download_csv(request):
    """
    View function to download weather data as a CSV file.
    If start_date and end_date are provided, data for that time range is returned.
    If last_24h is provided, data for the last 24 hours is returned.
    Otherwise, data for the last day is returned.
    """
    # Check if last_24h is requested
    if request.GET.get('last_24h'):
        berlin_tz = pytz.timezone('Europe/Berlin')
        end_date = datetime.now(berlin_tz)
        start_date = end_date - timedelta(hours=24)
        data = Dataset.objects.filter(added_on__range=[start_date, end_date])
    else:
        # Check if start_date and end_date are provided
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        # Set timezone to Berlin
        berlin_tz = pytz.timezone('Europe/Berlin')
        
        if start_date_str and end_date_str:
            try:
                # Parse dates and localize them to Berlin timezone
                start_date = berlin_tz.localize(datetime.strptime(start_date_str, '%Y-%m-%d'))
                # Add one day to end_date to make it inclusive
                end_date = berlin_tz.localize(datetime.strptime(end_date_str, '%Y-%m-%d')) + timedelta(days=1)
                
                # Validate time range (e.g., max 31 days)
                if (end_date - start_date).days > 32:  # 32 because we added one day to end_date
                    return HttpResponse("Time range too large. Maximum allowed range is 31 days.", status=400)
                
                # Query data for the specified time range
                data = Dataset.objects.filter(added_on__range=[start_date, end_date])
            except ValueError:
                return HttpResponse("Invalid date format. Use YYYY-MM-DD.", status=400)
        else:
            # If no date range is provided, get data for the last 1 day
            end_date = datetime.now(berlin_tz)
            start_date = end_date - timedelta(days=1)
            data = Dataset.objects.filter(added_on__range=[start_date, end_date])

    # Sort data by jd
    data = data.order_by('jd')
    
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="weather_data.csv"'
    
    # Create a CSV writer
    writer = csv.writer(response)
    
    # Write the header row
    writer.writerow(['JD', 'Temperature (°C)', 'Pressure (hPa)', 'Humidity (g/m³)', 'Illuminance (lx)', 'Wind Speed (m/s)', 'Rain', 'Note', 'Merged', 'Added On', 'Last Modified'])
    
    # Write the data rows
    for item in data:
        writer.writerow([
            item.jd,
            item.temperature,
            item.pressure,
            item.humidity,
            item.illuminance,
            item.wind_speed,
            item.rain,
            item.note,
            item.merged,
            item.added_on,
            item.last_modified
        ])
    
    return response
