############################################################################
#                               Libraries                                  #
############################################################################

import os

import sys

import time
import datetime

import numpy as np

import astropy.units as u
from astropy.time import Time
from astropy.timeseries import TimeSeries, aggregate_downsample

sys.path.append('../')
os.environ["DJANGO_SETTINGS_MODULE"] = "weather_station.settings"

import django

django.setup()

from datasets.models import Dataset
from django.db import transaction
from django.utils import timezone


############################################################################
#                                  Main                                    #
############################################################################

if __name__ == '__main__':
    #   Check command line arguments
    if len(sys.argv) not in [4, 5]:
        print(f'Only 3 command line arguments are supported. {len(sys.argv)-1} were provided.')
        sys.exit()

    arguments = sys.argv
    # for i, arg in enumerate(arguments):
    #     print(f"Argument {i:>6}: {arg}")

    #   Days to go back to merge the data 
    # days_to_go_back = 90
    # days_to_go_back = 0
    days_to_go_back = float(arguments[1])  

    #   Time span to merge
    merge_time_span = float(arguments[2])

    #   Bin size in seconds
    # bin_size = 600.
    bin_size = float(arguments[3])

    #   Set test variable
    if len(sys.argv) == 5 and arguments[4] == 'true':
        test_only = True
    else:
        test_only = False

    #   Load datasets
    jd_current = Time(datetime.datetime.now(datetime.timezone.utc)).jd

    #   Check provided time for consistency
    if days_to_go_back < merge_time_span:
        print(f'Provided times are inconsistent. The time span to merge is greater than the time span to go back.')
        sys.exit()

    #   Get requested range of data (unmerged), ordered by time
    data_range = Dataset.objects.filter(
        jd__range=[
            jd_current - days_to_go_back,
            jd_current - days_to_go_back + merge_time_span
        ],
        merged=False
    ).order_by('jd')
    # print(data_range)

    x_identifier = 'jd'
    # Include additional fields introduced in the model
    y_identifier_list = [
        'temperature',
        'pressure',
        'humidity',
        'illuminance',
        'wind_speed',
        'rain',
        'sky_temp',
        'box_temp',
        'is_raining',
        'co2_ppm',
        'tvoc_ppb',
    ]
    data = np.array(list(data_range.values_list(x_identifier, *y_identifier_list)))

    #   Verify that data was returned
    if data.size != 0:
        ts_time = Time(data[:, 0], format='jd')
        time_series_to_average = TimeSeries(
            time=ts_time,
            data={
                'temperature': data[:, 1],
                'pressure': data[:, 2],
                'humidity': data[:, 3],
                'illuminance': data[:, 4],
                'wind_speed': data[:, 5],
                'sky_temp': data[:, 7],
                'box_temp': data[:, 8],
                'co2_ppm': data[:, 10],
                'tvoc_ppb': data[:, 11],
            }
        )
        time_series_to_sum = TimeSeries(
            time=ts_time,
            data={'rain': data[:, 6]},
        )
        time_series_flag = TimeSeries(
            time=ts_time,
            data={'is_raining': data[:, 9]},
        )

        if len(time_series_to_average) and len(time_series_to_sum):
            time_series_averaged = aggregate_downsample(
                time_series_to_average,
                time_bin_size=float(bin_size) * u.s,
                aggregate_func=np.nanmedian,
            )

            time_series_summed = aggregate_downsample(
                time_series_to_sum,
                time_bin_size=float(bin_size) * u.s,
                aggregate_func=np.nansum,
            )

            time_series_flagged = aggregate_downsample(
                time_series_flag,
                time_bin_size=float(bin_size) * u.s,
                aggregate_func=np.nanmax,
            )

            # print(time_series_averaged)
            # print(time_series_to_average)
            # Build a robust mask across key averaged columns
            mask = np.invert(time_series_averaged['temperature'].mask)
            for col in ['pressure', 'humidity', 'illuminance', 'wind_speed']:
                mask = mask & np.invert(time_series_averaged[col].mask)

            # print(time_series_averaged)
            # Use bin midpoint for new records (start + bin_size/2)
            new_time_jd = time_series_averaged['time_bin_start'].value[mask] + (float(bin_size) / 86400.0) / 2.0
            averaged_temperature = time_series_averaged['temperature'].value[mask]
            averaged_pressure = time_series_averaged['pressure'].value[mask]
            averaged_humidity = time_series_averaged['humidity'].value[mask]
            averaged_illuminance = time_series_averaged['illuminance'].value[mask]
            averaged_wind_speed = time_series_averaged['wind_speed'].value[mask]
            averaged_sky_temp = time_series_averaged['sky_temp'].value[mask]
            averaged_box_temp = time_series_averaged['box_temp'].value[mask]
            averaged_co2_ppm = time_series_averaged['co2_ppm'].value[mask]
            averaged_tvoc_ppb = time_series_averaged['tvoc_ppb'].value[mask]
            summed_rain = time_series_summed['rain'].value[mask]
            flagged_raining = time_series_flagged['is_raining'].value[mask]

            # print('--------')
            # print(new_time_jd)
            # print(averaged_temperature)
            # print(summed_rain)
            # sys.exit()

            if not test_only:
                instances = []
                for i, new_jd in enumerate(new_time_jd):
                    # Convert JD midpoint to aware datetime (UTC)
                    dt_naive = Time(new_jd, format='jd').to_datetime()
                    dt_aware = timezone.make_aware(dt_naive, timezone=timezone.utc) if timezone.is_naive(dt_naive) else dt_naive

                    new_dataset = Dataset(
                        jd=float(new_jd),
                        temperature=float(averaged_temperature[i]) if not np.isnan(averaged_temperature[i]) else None,
                        pressure=float(averaged_pressure[i]) if not np.isnan(averaged_pressure[i]) else None,
                        humidity=float(averaged_humidity[i]) if not np.isnan(averaged_humidity[i]) else None,
                        illuminance=float(averaged_illuminance[i]) if not np.isnan(averaged_illuminance[i]) else None,
                        wind_speed=float(averaged_wind_speed[i]) if not np.isnan(averaged_wind_speed[i]) else None,
                        rain=float(summed_rain[i]) if not np.isnan(summed_rain[i]) else 0.0,
                        sky_temp=float(averaged_sky_temp[i]) if not np.isnan(averaged_sky_temp[i]) else None,
                        box_temp=float(averaged_box_temp[i]) if not np.isnan(averaged_box_temp[i]) else None,
                        is_raining=int(flagged_raining[i]) if not np.isnan(flagged_raining[i]) else 0,
                        co2_ppm=int(np.rint(averaged_co2_ppm[i])) if not np.isnan(averaged_co2_ppm[i]) else 0,
                        tvoc_ppb=int(np.rint(averaged_tvoc_ppb[i])) if not np.isnan(averaged_tvoc_ppb[i]) else 0,
                        merged=True,
                        added_on=dt_aware,
                    )
                    instances.append(new_dataset)

                with transaction.atomic():
                    Dataset.objects.bulk_create(instances, batch_size=1000)
                    # Remove original unmerged rows in the processed window
                    data_range.delete()
