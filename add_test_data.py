###
#   Test data upload script
#
import requests

import time
import datetime
from astropy.time import Time

import environ

# Initialise environment variables
env = environ.Env()
environ.Env.read_env()

URL = env('URL')

username=env("USER")
password=env("PASSWORD")

#   Initial data values
init_temp = 30.
init_pressu = 1000.
init_humi = 30.
init_illum = 10000.
init_velo = 20.

for i in range(0,1380):
    #   Get current Julian date
    jd = Time(datetime.datetime.now(datetime.timezone.utc)).jd

    #   Prepare data
    data = {
        'jd':jd,
        'temperature':init_temp-0.03*i,
        'pressure':init_pressu+0.05*i,
        'humidity':init_humi-0.01*i,
        'illuminance':init_illum-1.*i,
        'wind_speed':init_velo+0.1*i,
#         'wind_speed':float('NaN'),
        'rain':1.25,
        }

    #   Add data
    response = requests.post(URL, auth=(username, password), data=data)
    print(i, jd, response.status_code)

    time.sleep(10.)
