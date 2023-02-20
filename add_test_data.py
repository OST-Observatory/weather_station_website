###  TEST script ###

import requests

import time
import datetime
from astropy.time import Time

import environ

# Initialise environment variables
env = environ.Env()
environ.Env.read_env()

URL = 'http://127.0.0.1:8000/api/datasets/'

username=env("USER")
password=env("PASSWORD")

#   Initial data values
init_temp = 30.
init_pressu = 1000.
init_humi = 30.
init_illum = 10000.
init_velo = 20.

for i in range(0,100):
    #   Get current Julian date
    jd = Time(datetime.datetime.now(datetime.timezone.utc)).jd

    #   Prepare data
    data = {
        'jd':jd,
        'temperature':init_temp-0.3*i,
        'pressure':init_pressu+5.*i,
        'humidity':init_humi-0.1*i,
        'illuminance':init_illum-30.*i,
        'wind_speed':init_velo+5.*i,
        }

    #   Add data
    response = requests.post(URL, auth=(username, password), data=data)
    print(i, response.status_code)

    time.sleep(100.)
