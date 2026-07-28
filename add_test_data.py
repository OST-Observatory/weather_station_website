###
#   Test data upload script (WEATHER-HMAC-V1)
#
import hashlib
import hmac
import secrets
import time
import datetime
from astropy.time import Time
import math
import random
import os
from urllib.parse import urlencode

import requests
import environ

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env = environ.Env()
environ.Env.read_env(os.path.join(_BASE_DIR, 'weather_station', '.env'))
environ.Env.read_env(os.path.join(_BASE_DIR, '.env'))

# Development:  http://127.0.0.1:8010/weather_api/datasets/
# Production:    https://…/weather_station/weather_api/datasets/
URL = env('URL').rstrip('/') + '/'
DEVICE_ID = env('UPLOAD_DEVICE_ID')
KEY_ID = env('UPLOAD_KEY_ID')
SECRET_HEX = env('UPLOAD_HMAC_SECRET_HEX').strip().replace('\r', '')
CANONICAL_PATH = env(
    'UPLOAD_HMAC_CANONICAL_PATH',
    default='/weather_station/weather_api/datasets/',
)


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def encode_and_sign(data):
    body = urlencode(list(data.items()), doseq=False).encode('utf-8')
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    body_digest = hashlib.sha256(body).hexdigest()
    canonical = '\n'.join([
        'WEATHER-HMAC-V1',
        'POST',
        CANONICAL_PATH,
        'application/x-www-form-urlencoded',
        DEVICE_ID,
        KEY_ID,
        ts,
        nonce,
        body_digest,
    ])
    secret = bytes.fromhex(SECRET_HEX)
    signature = hmac.new(secret, canonical.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Weather-Device': DEVICE_ID,
        'X-Weather-Key-Id': KEY_ID,
        'X-Weather-Timestamp': ts,
        'X-Weather-Nonce': nonce,
        'X-Weather-Signature': signature,
    }
    return body, headers


print(f"[INFO] Upload URL: {URL}")
print(f"[INFO] Device: {DEVICE_ID} key={KEY_ID}")

start_dt = datetime.datetime.now(datetime.timezone.utc)
session = requests.Session()


def post_with_retries(url, body, headers, max_retries=5, base_delay=1.0, timeout=10.0):
    for attempt in range(max_retries):
        try:
            resp = session.post(url, data=body, headers=headers, timeout=timeout)
            if resp.status_code in (502, 503, 504) or resp.status_code >= 500:
                raise requests.HTTPError(f"Server error {resp.status_code}")
            if resp.status_code == 429:
                try:
                    wait = float(resp.headers.get('Retry-After', ''))
                except Exception:
                    wait = None
                time.sleep(
                    wait if wait and wait > 0
                    else min(60.0, base_delay * (2 ** attempt) + random.uniform(0, 1))
                )
                continue
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            delay = min(60.0, base_delay * (2 ** attempt) + random.uniform(0, 1))
            print(f"Post failed (attempt {attempt+1}/{max_retries}): {exc}. Retrying in {delay:.1f}s ...")
            time.sleep(delay)
        except Exception as exc:
            print(f"Unexpected error while posting: {exc}")
            break
    return None


for i in range(0, 1380):
    current_dt = start_dt + datetime.timedelta(seconds=10 * i)
    jd = Time(current_dt).jd

    hour_utc = (current_dt.hour + current_dt.minute / 60.0 + current_dt.second / 3600.0)
    day_angle = 2 * math.pi * (hour_utc / 24.0)
    daylight_factor = max(0.0, math.sin(day_angle))
    night_factor = max(0.0, -math.sin(day_angle))

    temperature = 18.0 + 6.0 * math.sin(day_angle - math.pi / 2) + random.gauss(0, 0.3)
    sky_temp = temperature - (8.0 + 7.0 * night_factor) + random.gauss(0, 0.5)
    box_temp = temperature + 1.5 * daylight_factor + random.gauss(0, 0.2)
    pressure = 1013.0 + 3.0 * math.sin(2 * math.pi * (hour_utc / 24.0 + 0.1)) + random.gauss(0, 0.3)
    humidity = clamp(70.0 - 15.0 * daylight_factor + random.gauss(0, 3.0), 10.0, 100.0)

    phase = i % 800
    in_drizzle_window = 50 <= phase <= 170
    in_rain_window = 400 <= phase <= 520
    is_raining = 1 if (in_drizzle_window or in_rain_window) else 0

    illuminance_clear = 80000.0 * (daylight_factor ** 1.5)
    illuminance = illuminance_clear * (0.35 if is_raining else 1.0)
    illuminance += random.gauss(0, 500.0)
    illuminance = max(0.0, illuminance)

    wind_speed = max(0.0, 2.0 + 1.5 * daylight_factor + random.gauss(0, 0.5))

    if in_drizzle_window:
        rain = 0.0
    elif in_rain_window:
        rain = max(0.0, 1.25 + random.gauss(0, 0.1))
    else:
        rain = 0.0

    pm1_0 = int(round(clamp(8.0 + random.gauss(0, 3.0), 0.0, 100.0)))
    pm2_5 = int(round(clamp(12.0 + random.gauss(0, 5.0), 0.0, 150.0)))
    pm10 = int(round(clamp(18.0 + random.gauss(0, 6.0), 0.0, 200.0)))
    uv_index = int(round(clamp(3.0 + 4.0 * daylight_factor + random.gauss(0, 0.5), 0.0, 11.0)))

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
        'pm1_0': pm1_0,
        'pm2_5': pm2_5,
        'pm10': pm10,
        'uv_index': uv_index,
    }

    body, headers = encode_and_sign(data)
    response = post_with_retries(URL, body, headers)
    if response is None:
        print(i, jd, "failed after retries")
    elif response.status_code in (200, 201):
        print(i, jd, response.status_code)
    else:
        print(i, jd, response.status_code, response.text[:300])
        if response.status_code == 404:
            print(
                "  Hint: 404 often means wrong URL. In production include "
                "/weather_station/ before /weather_api/ (see comment at top)."
            )

    time.sleep(10.0)
