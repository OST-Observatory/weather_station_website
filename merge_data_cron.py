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

    #   Get requested range of data
    data_range = Dataset.objects.filter(
        jd__range=[
            jd_current - days_to_go_back,
            jd_current - days_to_go_back + merge_time_span
        ]
    ).filter(
        merged=False
    )
    # print(data_range)

    x_identifier = 'jd'
    y_identifier_list = [
        'temperature',
        'pressure',
        'humidity',
        'illuminance',
        'wind_speed',
        'rain',
    ]
    data = np.array(data_range.values_list(x_identifier, *y_identifier_list))

    #   Verify that data was returned
    if data.size != 0:
        time_series_to_average = TimeSeries(
            time=Time(data[:, 0], format='jd'),
            data={
                'temperature': data[:, 1],
                'pressure': data[:, 2],
                'humidity': data[:, 3],
                'illuminance': data[:, 4],
                'wind_speed': data[:, 5]
            }
        )
        time_series_to_sum = TimeSeries(
            time=Time(data[:, 0], format='jd'),
            data={
                'rain': data[:, 6]
            }
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

            # print(time_series_averaged)
            # print(time_series_to_average)
            mask = np.invert(time_series_averaged['temperature'].mask)
            if mask is None:
                mask = True

            # print(time_series_averaged)
            new_time_jd = time_series_averaged['time_bin_start'].value[mask]
            averaged_temperature = time_series_averaged['temperature'].value[mask]
            averaged_pressure = time_series_averaged['pressure'].value[mask]
            averaged_humidity = time_series_averaged['humidity'].value[mask]
            averaged_illuminance = time_series_averaged['illuminance'].value[mask]
            averaged_wind_speed = time_series_averaged['wind_speed'].value[mask]
            summed_rain = time_series_summed['rain'].value[mask]

            # print('--------')
            # print(new_time_jd)
            # print(averaged_temperature)
            # print(summed_rain)
            # sys.exit()

            for i, new_jd in enumerate(new_time_jd):
                print(
                    new_jd,
                    averaged_temperature[i],
                    averaged_pressure[i],
                    averaged_humidity[i],
                    averaged_illuminance[i],
                    averaged_wind_speed[i],
                    summed_rain[i]
                )

                if not test_only:
                    # new_dataset = Dataset.objects.create(
                    #     jd=new_jd,
                    #     temperature=averaged_temperature[i],
                    #     pressure=averaged_pressure[i],
                    #     humidity=averaged_humidity[i],
                    #     illuminance=averaged_illuminance[i],
                    #     wind_speed=averaged_wind_speed[i],
                    #     rain=summed_rain[i],
                    # )
                    new_dataset = Dataset(
                        jd=new_jd,
                        temperature=averaged_temperature[i],
                        pressure=averaged_pressure[i],
                        humidity=averaged_humidity[i],
                        illuminance=averaged_illuminance[i],
                        wind_speed=averaged_wind_speed[i],
                        rain=summed_rain[i],
                        merged=True,
                    )
                    new_dataset.save()
                    time.sleep(0.01)

            if not test_only:
                # sys.exit()
                #   Loop over old datasets to be removed
                for dataset in data_range:
                    dataset.delete()
