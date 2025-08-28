###
#   Test data upload script
#
import requests

import time
import datetime
from astropy.time import Time
import math
import random

import environ

# Initialise environment variables
env = environ.Env()
environ.Env.read_env()

URL = env('URL')

username=env("WEATHERUSER")
password=env("PASSWORD")


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


#   Simulate ~3.8h in 10s steps (1380 samples)
start_dt = datetime.datetime.now(datetime.timezone.utc)

#   Reuse HTTP connection
session = requests.Session()

def post_with_retries(url, auth, data, max_retries=5, base_delay=1.0, timeout=10.0):
    for attempt in range(max_retries):
        try:
            resp = session.post(url, auth=auth, data=data, timeout=timeout)
            # Retry on server/transient errors
            if resp.status_code in (502, 503, 504) or resp.status_code >= 500:
                raise requests.HTTPError(f"Server error {resp.status_code}")
            if resp.status_code == 429:
                # Respect Retry-After if present
                try:
                    wait = float(resp.headers.get('Retry-After', ''))
                except Exception:
                    wait = None
                time.sleep(wait if wait and wait > 0 else min(60.0, base_delay * (2 ** attempt) + random.uniform(0, 1)))
                continue
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            # Server restarting or transient network issue – backoff and retry
            delay = min(60.0, base_delay * (2 ** attempt) + random.uniform(0, 1))
            print(f"Post failed (attempt {attempt+1}/{max_retries}): {exc}. Retrying in {delay:.1f}s ...")
            time.sleep(delay)
        except Exception as exc:
            print(f"Unexpected error while posting: {exc}")
            break
    return None

for i in range(0, 1380):
    #   Simulated current time advances by 10 seconds per step
    current_dt = start_dt + datetime.timedelta(seconds=10 * i)
    jd = Time(current_dt).jd

    #   Diurnal cycle proxy (based on UTC hour)
    hour_utc = (current_dt.hour + current_dt.minute / 60.0 + current_dt.second / 3600.0)
    day_angle = 2 * math.pi * (hour_utc / 24.0)
    daylight_factor = max(0.0, math.sin(day_angle))          # 0 (night) .. 1 (midday)
    night_factor = max(0.0, -math.sin(day_angle))            # 0 (day) .. 1 (midnight)

    #   Temperature (°C): base + diurnal + small noise
    temperature = 18.0 + 6.0 * math.sin(day_angle - math.pi / 2) + random.gauss(0, 0.3)

    #   Sky temperature (°C): typically below ambient, especially at night
    sky_temp = temperature - (8.0 + 7.0 * night_factor) + random.gauss(0, 0.5)

    #   Box temperature (°C): slightly above ambient during day
    box_temp = temperature + 1.5 * daylight_factor + random.gauss(0, 0.2)

    #   Pressure (hPa): slow variation + tiny noise
    pressure = 1013.0 + 3.0 * math.sin(2 * math.pi * (hour_utc / 24.0 + 0.1)) + random.gauss(0, 0.3)

    #   Humidity [%]: higher at night, lower during day
    humidity = clamp(70.0 - 15.0 * daylight_factor + random.gauss(0, 3.0), 10.0, 100.0)

    #   Periodic precipitation pattern over ~133 minutes (period = 800 steps)
    #   - Drizzle window: drop sensor active, but no measurable rain amount
    #   - Rain window: drop sensor active with measurable rain amount
    #   (window length ~120 steps = 20min)
    phase = i % 800
    in_drizzle_window = 50 <= phase <= 170
    in_rain_window = 400 <= phase <= 520
    is_raining = 1 if (in_drizzle_window or in_rain_window) else 0

    #   Illuminance (lx): strong during day, near zero at night; reduced when raining
    illuminance_clear = 80000.0 * (daylight_factor ** 1.5)
    illuminance = illuminance_clear * (0.35 if is_raining else 1.0)
    illuminance += random.gauss(0, 500.0)
    illuminance = max(0.0, illuminance)

    #   Wind speed (arbitrary scale or m/s): slightly higher during day + gust noise
    wind_speed = max(0.0, 2.0 + 1.5 * daylight_factor + random.gauss(0, 0.5))

    #   Rain (uncalibrated):
    #   - Drizzle: 0.0 (so Bokeh-Bins mit Summe==0 bleiben als Drizzle markierbar)
    #   - Rain: >0
    #   - None: 0.0
    if in_drizzle_window:
        rain = 0.0
    elif in_rain_window:
        rain = max(0.0, 1.25 + random.gauss(0, 0.1))
    else:
        rain = 0.0

    #   CO2 (ppm): outdoor-like background around ~420 ppm
    co2_ppm = int(round(clamp(420.0 + random.gauss(0, 6.0), 380.0, 520.0)))

    #   TVOC (ppb): low outdoors, slightly variable
    tvoc_ppb = int(round(clamp(50.0 + random.gauss(0, 25.0), 5.0, 300.0)))

    data = {
        'jd': jd,
        'temperature': temperature,
        'pressure': pressure,
        'humidity': humidity,
        'illuminance': illuminance,
        'wind_speed': wind_speed,
        'sky_temp': sky_temp,
        'box_temp': box_temp,
        'rain': rain,
        'is_raining': is_raining,
        'co2_ppm': co2_ppm,
        'tvoc_ppb': tvoc_ppb,
    }

    response = post_with_retries(URL, auth=(username, password), data=data)
    if response is None:
        print(i, jd, "failed after retries")
    else:
        print(i, jd, response.status_code)

    time.sleep(10.0)
