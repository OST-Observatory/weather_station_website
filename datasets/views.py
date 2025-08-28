import os
import time
import numpy as np
import astropy.coordinates as coord
from astropy.time import Time
import astropy.units as u
from django.db.models import Max, Sum, Avg

# Constants
WIND_ROTATIONS_TO_MPS = 0.14
from django.shortcuts import render
from astroplan import Observer
from astropy.coordinates import get_body
from functools import lru_cache
from zoneinfo import ZoneInfo
from .plots import default_plots
from .forms import ParameterPlotForm, DateRangeForm
from .models import Dataset
from datetime import datetime, timedelta, timezone


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
    # Add note if resolution was auto-adjusted
    if parameters.get('resolution_adjusted'):
        adjusted_to = int(float(parameters.get('adjusted_to', 0)))
        div['note'] = f"Time resolution was increased to {adjusted_to}s to keep plots responsive."

    ###
    #   Sunrise and sunset
    #

    #   Location
    location = coord.EarthLocation(lat=+52.409184, lon=+12.973185, height=39)

    #   Define the location by means of astroplan
    ost = Observer(location=location, name="OST", timezone="Europe/Berlin")

    #   Current time
    current_time = Time.now()

    @lru_cache(maxsize=16)
    def get_sun_times_for_date(jd_day_key: int):
        t = Time(jd_day_key, format='jd')
        sunset = ost.sun_set_time(
            t,
            horizon=-0.8333 * u.deg,
            which='nearest',
        )
        sunrise = ost.sun_rise_time(
            t,
            horizon=-0.8333 * u.deg,
            which='nearest',
        )
        return sunrise, sunset

    sunrise_tonight, sunset_tonight = get_sun_times_for_date(int(current_time.jd))

    #   Prepare strings for sunrise and sunset output
    berlin_tz = ZoneInfo('Europe/Berlin')
    sunrise_local = sunrise_tonight.to_datetime(timezone=berlin_tz)
    sunset_local = sunset_tonight.to_datetime(timezone=berlin_tz)
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

        wind_avg = Dataset.objects.filter(
            jd__range=[latest_data.jd-0.001388889, latest_data.jd]
        ).aggregate(avg=Avg('wind_speed'))['avg'] or 0.0
        wind_speed = f'{wind_avg * WIND_ROTATIONS_TO_MPS:.0f}'

    except:
        temperature, pressure, humidity, illuminance = '0', '0', '0', '0'
        wind_speed = '0'

    #   Setup date string from local time
    local_time = datetime.now(berlin_tz)
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
    #   Weather icon selection
    #
    def select_icon(latest):
        try:
            # Determine day/night using sunrise/sunset
            now_ts = datetime.now().timestamp()
            is_day = sunrise_tonight.datetime.timestamp() <= now_ts <= sunset_tonight.datetime.timestamp()

            # Latest measurements (numeric)
            temp_c = float(getattr(latest, 'temperature', 0.0) or 0.0)
            sky_c = getattr(latest, 'sky_temp', None)
            if sky_c is not None:
                try:
                    sky_c = float(sky_c)
                except Exception:
                    sky_c = None
            # Cloud proxy: ambient - sky (higher means clearer sky)
            delta_t = None
            if sky_c is not None:
                delta_t = temp_c - sky_c

            # Dew point (Magnus formula) for fog detection
            def compute_dew_point(temp_c_val: float, humi_percent: float) -> float:
                a, b = 17.62, 243.12
                humi_clamped = max(0.1, min(100.0, humi_percent))
                gamma = (a * temp_c_val) / (b + temp_c_val) + np.log(humi_clamped / 100.0)
                return (b * gamma) / (a - gamma)

            dp_c = compute_dew_point(temp_c, float(getattr(latest, 'humidity', 0.0) or 0.0))

            # Recent rain (uncalibrated counts) over last 30 minutes
            jd_window = 30.0 / (24.0 * 60.0)
            recent = Dataset.objects.filter(jd__range=[latest.jd - jd_window, latest.jd])
            recent_rain_sum = recent.aggregate(total=Sum('rain'))['total'] or 0.0
            is_raining_flag = int(getattr(latest, 'is_raining', 0) or 0) == 1

            # Wind speed (approx m/s) from previous computation
            try:
                wind_gust_two_minutes = Dataset.objects.filter(
                    jd__range=[latest.jd - 0.001388889, latest.jd]
                ).values_list("wind_speed")
                wind_mps = float(np.mean(wind_gust_two_minutes)) * 0.14
            except Exception:
                wind_mps = 0.0

            # Precipitation type by temperature
            def precip_icon_base():
                if temp_c <= 0.5:
                    return 'snow'
                if temp_c < 2.5:
                    return 'sleet'
                return 'rain'

            # Intensity
            heavy_precip = recent_rain_sum >= 10.0  # heuristic on raw counts
            windy = wind_mps >= 8.0

            # Start with precipitation if detected
            if is_raining_flag or recent_rain_sum > 0.0:
                base = precip_icon_base()
                if base == 'snow':
                    if windy:
                        return ('wi-snow-wind', 'Snow with wind')
                    return ('wi-night-snow' if not is_day else 'wi-day-snow', 'Snow')
                if base == 'sleet':
                    return (
                        'wi-night-sleet' if not is_day else 'wi-day-sleet',
                        'Sleet / freezing rain'
                    )
                # rain
                if windy:
                    return (
                        'wi-night-alt-rain-wind' if not is_day else 'wi-day-rain-wind',
                        'Rain with wind'
                    )
                if heavy_precip:
                    return (
                        'wi-night-storm-showers' if not is_day else 'wi-day-storm-showers',
                        'Heavy rain'
                    )
                return (
                    'wi-night-sprinkle' if not is_day else 'wi-day-sprinkle',
                    'Light rain / drizzle'
                )

            # Fog/Mist: temperature close to dew point and no recent rain
            try:
                if (temp_c - dp_c) <= 1.5 and recent_rain_sum == 0.0:
                    return (
                        'wi-day-fog' if is_day else 'wi-night-fog',
                        'Fog'
                    )
            except Exception:
                pass

            # No precipitation: decide clouds via delta_t
            if delta_t is None:
                # Fallback to simple day/night clear
                return (
                    'wi-night-clear' if not is_day else 'wi-day-sunny',
                    'Clear'
                )

            # Heuristic thresholds for cloud cover proxy
            if delta_t >= 15.0:
                if is_day:
                    return ('wi-day-sunny', 'Clear')
                # Night: choose moon phase icon for clear sky
                try:
                    t_now = Time.now()
                    phase_angle = float(get_body('moon', t_now).separation(get_body('sun', t_now)).deg)
                    def map_moon_icon(angle_deg: float) -> str:
                        # 0=new, 90=first quarter, 180=full, 270=last quarter
                        if angle_deg < 22.5 or angle_deg >= 337.5:
                            return 'wi-moon-new'
                        if angle_deg < 67.5:
                            return 'wi-moon-waxing-crescent-3'
                        if angle_deg < 112.5:
                            return 'wi-moon-first-quarter'
                        if angle_deg < 157.5:
                            return 'wi-moon-waxing-gibbous-3'
                        if angle_deg < 202.5:
                            return 'wi-moon-full'
                        if angle_deg < 247.5:
                            return 'wi-moon-waning-gibbous-3'
                        if angle_deg < 292.5:
                            return 'wi-moon-third-quarter'
                        return 'wi-moon-waning-crescent-3'
                    return (map_moon_icon(phase_angle), 'Clear')
                except Exception:
                    return ('wi-night-clear', 'Clear')
            if delta_t >= 12.0:
                return (
                    'wi-night-alt-partly-cloudy' if not is_day else 'wi-day-sunny-overcast',
                    'Mostly clear'
                )
            if delta_t >= 6.0:
                return (
                    'wi-night-alt-partly-cloudy' if not is_day else 'wi-day-cloudy',
                    'Partly cloudy'
                )
            if delta_t >= 3.0:
                return ('wi-night-cloudy' if not is_day else 'wi-day-cloudy', 'Cloudy')
            return ('wi-cloudy', 'Overcast')
        except Exception:
            return ('wi-day-sunny', 'Clear')

    icon_class, icon_title = select_icon(latest_data) if added_on__max else ('wi-day-sunny', 'Clear')

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
        'icon_class': icon_class,
        'icon_title': icon_title,
        'form': form,
        'date_form': date_form
    }

    return render(request, 'datasets/dashboard.html', context)
