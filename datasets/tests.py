import base64
from datetime import date, timedelta
from unittest.mock import patch

from astropy.time import Time
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Dataset
from .plot_cache import plot_cache_enabled
from .plot_db import fetch_binned_rows, should_use_postgres_binning
from .plots import default_plots


@override_settings(UPLOAD_AUTH_MODE='dual')
class DatasetAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='data_upload_user',
            password='test-password',
        )
        self.client = APIClient()
        self.create_url = reverse('datasets-api:dataset-create')
        self.detail_url = reverse('datasets-api:dataset-detail', kwargs={'pk': 1})
        self.last_url = reverse('datasets-api:last_dataset')
        self.download_url = reverse('datasets-api:download-csv')

    def _auth_header(self):
        token = base64.b64encode(b'data_upload_user:test-password').decode('ascii')
        return {'HTTP_AUTHORIZATION': f'Basic {token}'}

    def _sample_payload(self, **overrides):
        payload = {
            'jd': Time.now().jd,
            'temperature': 12.5,
            'pressure': 1013.0,
            'humidity': 55.0,
            'illuminance': 1000.0,
            'wind_speed': 3.0,
            'sky_temp': 10.0,
            'box_temp': 15.0,
            'rain': 0.0,
            'is_raining': 0,
            'pm1_0': 8,
            'pm2_5': 12,
            'pm10': 18,
            'uv_index': 3,
        }
        payload.update(overrides)
        return payload

    def test_create_dataset_authenticated(self):
        response = self.client.post(
            self.create_url,
            self._sample_payload(),
            format='json',
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Dataset.objects.count(), 1)

    def test_create_dataset_unauthenticated(self):
        response = self.client.post(
            self.create_url,
            self._sample_payload(),
            format='json',
        )
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_update_delete_forbidden(self):
        dataset = Dataset.objects.create(**self._sample_payload())
        detail_url = reverse('datasets-api:dataset-detail', kwargs={'pk': dataset.pk})

        put_response = self.client.put(
            detail_url,
            self._sample_payload(temperature=20.0),
            format='json',
            **self._auth_header(),
        )
        delete_response = self.client.delete(detail_url, **self._auth_header())

        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_last_dataset_empty_db(self):
        response = self.client.get(self.last_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_last_dataset_multiple_same_added_on(self):
        shared_added_on = timezone.now()
        older = Dataset.objects.create(
            **self._sample_payload(jd=Time.now().jd - 0.01),
            added_on=shared_added_on,
        )
        newer = Dataset.objects.create(
            **self._sample_payload(jd=Time.now().jd),
            added_on=shared_added_on,
        )

        response = self.client.get(self.last_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['pk'], newer.pk)
        self.assertNotEqual(response.data['pk'], older.pk)

    def test_download_csv_invalid_range(self):
        start = date.today() - timedelta(days=40)
        end = date.today()
        response = self.client.get(self.download_url, {
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'dl': 'csv',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_serializer_readonly_merged(self):
        response = self.client.post(
            self.create_url,
            self._sample_payload(merged=True),
            format='json',
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Dataset.objects.get().merged)

    def test_create_dataset_accepts_anemometer_revolutions(self):
        response = self.client.post(
            self.create_url,
            self._sample_payload(wind_speed=139.0),
            format='json',
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Dataset.objects.get().wind_speed, 139.0)

    def test_create_dataset_rejects_excessive_wind_revolutions(self):
        response = self.client.post(
            self.create_url,
            self._sample_payload(wind_speed=501.0),
            format='json',
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DashboardTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch('datasets.views.Observer')
    def test_dashboard_no_data(self, mock_observer_cls):
        observer = mock_observer_cls.return_value
        observer.sun_rise_time.return_value = Time('2026-04-16 04:30:00')
        observer.sun_set_time.return_value = Time('2026-04-16 20:15:00')

        response = Client().get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clear')
        self.assertContains(response, 'wi-day-sunny')
        self.assertContains(response, 'Expand to load additional plots')

    @patch('datasets.views.Observer')
    def test_dashboard_fresh_query_ignored_for_anonymous(self, mock_observer_cls):
        observer = mock_observer_cls.return_value
        observer.sun_rise_time.return_value = Time('2026-04-16 04:30:00')
        observer.sun_set_time.return_value = Time('2026-04-16 20:15:00')

        params = {
            'plot_range': '0.5',
            'time_resolution': '300',
        }
        with patch('datasets.views.default_plots', wraps=default_plots) as mocked:
            Client().get(reverse('dashboard'), {**params, 'fresh': '1'})
            self.assertEqual(mocked.call_count, 1)
            self.assertFalse(mocked.call_args_list[0].kwargs.get('fresh'))

    @patch('datasets.views.Observer')
    def test_dashboard_clean_url_exposes_plot_defaults(self, mock_observer_cls):
        observer = mock_observer_cls.return_value
        observer.sun_rise_time.return_value = Time('2026-04-16 04:30:00')
        observer.sun_set_time.return_value = Time('2026-04-16 20:15:00')

        response = Client().get(reverse('dashboard'))
        self.assertContains(response, '"plot_range": "0.5"')
        self.assertContains(response, '"time_resolution": "300"')

    def test_additional_plots_without_query_uses_defaults(self):
        Dataset.objects.create(
            jd=Time.now().jd,
            temperature=10.0,
            pressure=1010.0,
            humidity=50.0,
            illuminance=100.0,
            wind_speed=1.0,
            sky_temp=8.0,
            box_temp=12.0,
            rain=0.0,
            is_raining=0,
            pm1_0=8,
            pm2_5=12,
            pm10=18,
            uv_index=3,
        )
        response = APIClient().get(reverse('datasets-api:additional-plots'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('figures', response.data)

    def test_additional_plots_empty_database(self):
        response = APIClient().get(reverse('datasets-api:additional-plots'), {
            'plot_range': '0.5',
            'time_resolution': '300',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('script'), '')
        self.assertEqual(response.data.get('figures'), {})

    def test_additional_plots_ignores_csrf_query_param(self):
        Dataset.objects.create(
            jd=Time.now().jd,
            temperature=10.0,
            pressure=1010.0,
            humidity=50.0,
            illuminance=100.0,
            wind_speed=1.0,
            sky_temp=8.0,
            box_temp=12.0,
            rain=0.0,
            is_raining=0,
            pm1_0=8,
            pm2_5=12,
            pm10=18,
            uv_index=3,
        )
        response = APIClient().get(reverse('datasets-api:additional-plots'), {
            'plot_range': '0.5',
            'time_resolution': '300',
            'csrfmiddlewaretoken': 'should-be-ignored',
            'start_date': '',
            'end_date': '',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('datasets.views.Observer')
    def test_additional_plots_endpoint(self, mock_observer_cls):
        observer = mock_observer_cls.return_value
        observer.sun_rise_time.return_value = Time('2026-04-16 04:30:00')
        observer.sun_set_time.return_value = Time('2026-04-16 20:15:00')

        Dataset.objects.create(
            jd=Time.now().jd,
            temperature=10.0,
            pressure=1010.0,
            humidity=50.0,
            illuminance=100.0,
            wind_speed=1.0,
            sky_temp=8.0,
            box_temp=12.0,
            rain=0.0,
            is_raining=0,
            pm1_0=8,
            pm2_5=12,
            pm10=18,
            uv_index=3,
        )
        response = APIClient().get(reverse('datasets-api:additional-plots'), {
            'plot_range': '0.5',
            'time_resolution': '300',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('script', response.data)
        self.assertIn('figures', response.data)
        self.assertIn('temp_combined', response.data['figures'])
        self.assertIn('uv_index', response.data['figures'])
        for key, div_html in response.data['figures'].items():
            if key == 'note':
                continue
            self.assertIn('id="', div_html)
            div_id = div_html.split('id="', 1)[1].split('"', 1)[0]
            self.assertIn(div_id, response.data['script'])


class PlotDbTests(TestCase):
    def test_should_use_postgres_binning_sqlite(self):
        self.assertFalse(should_use_postgres_binning(7))

    @patch('datasets.plot_db.is_postgresql', return_value=True)
    def test_should_use_postgres_binning_long_range(self, _mock_pg):
        self.assertFalse(should_use_postgres_binning(0.5))
        self.assertTrue(should_use_postgres_binning(7))

    def test_fetch_binned_rows_rejects_unknown_column(self):
        with self.assertRaises(ValueError):
            fetch_binned_rows(0.0, 1.0, 300, ['not_a_field'])

    def test_fetch_binned_rows_accepts_numpy_jd_scalars(self):
        import numpy as np
        from unittest.mock import MagicMock, patch

        jd = Time.now().jd
        Dataset.objects.create(
            jd=float(jd),
            temperature=10.0,
            pressure=1010.0,
            humidity=50.0,
            illuminance=100.0,
            wind_speed=1.0,
            rain=0.0,
            is_raining=0,
        )
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(float(jd), 10.0)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch('datasets.plot_db.is_postgresql', return_value=True), patch(
            'datasets.plot_db.connection', mock_conn,
        ):
            fetch_binned_rows(
                np.float64(jd - 1),
                np.float64(jd),
                300,
                ['temperature'],
            )

        sql_params = mock_cursor.execute.call_args[0][1]
        self.assertIsInstance(sql_params[0], float)
        self.assertNotEqual(type(sql_params[0]).__module__, 'numpy')


class PlotCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_plot_cache_fine_resolution_bypass(self):
        self.assertFalse(plot_cache_enabled(time_resolution=1, fresh=False))
        self.assertFalse(plot_cache_enabled(time_resolution=30, fresh=False))

    def test_plot_cache_coarse_enabled(self):
        self.assertTrue(plot_cache_enabled(time_resolution=60, fresh=False))
        self.assertTrue(plot_cache_enabled(time_resolution=300, fresh=False))

    def test_plot_cache_fresh_bypass(self):
        self.assertFalse(plot_cache_enabled(time_resolution=300, fresh=True))

    @override_settings(PLOT_CACHE_TTL_SECONDS=300)
    def test_plot_cache_coarse_live_hits(self):
        jd = Time.now().jd
        Dataset.objects.create(
            jd=jd,
            temperature=12.0,
            pressure=1013.0,
            humidity=55.0,
            illuminance=500.0,
            wind_speed=2.0,
            rain=0.0,
            is_raining=0,
        )
        params = {
            'plot_range': 0.041666667,
            'time_resolution': '300',
        }
        _, _, first_meta = default_plots(fresh=False, **params)
        _, _, second_meta = default_plots(fresh=False, **params)
        self.assertFalse(first_meta['cache_hit'])
        self.assertTrue(second_meta['cache_hit'])

    @override_settings(PLOT_CACHE_TTL_SECONDS=300)
    def test_plot_cache_fine_resolution_no_hit(self):
        jd = Time.now().jd
        Dataset.objects.create(
            jd=jd,
            temperature=12.0,
            pressure=1013.0,
            humidity=55.0,
            illuminance=500.0,
            wind_speed=2.0,
            rain=0.0,
            is_raining=0,
        )
        params = {
            'plot_range': 0.041666667,
            'time_resolution': '1',
        }
        _, _, first_meta = default_plots(fresh=False, **params)
        _, _, second_meta = default_plots(fresh=False, **params)
        self.assertFalse(first_meta['cache_enabled'])
        self.assertFalse(second_meta['cache_hit'])

    @override_settings(PLOT_CACHE_TTL_SECONDS=300)
    def test_plot_cache_invalidates_on_new_row(self):
        jd = Time.now().jd
        Dataset.objects.create(
            jd=jd - 0.001,
            temperature=12.0,
            pressure=1013.0,
            humidity=55.0,
            illuminance=500.0,
            wind_speed=2.0,
            rain=0.0,
            is_raining=0,
        )
        params = {
            'plot_range': 0.5,
            'time_resolution': '300',
        }
        default_plots(fresh=False, **params)
        Dataset.objects.create(
            jd=jd,
            temperature=13.0,
            pressure=1014.0,
            humidity=56.0,
            illuminance=600.0,
            wind_speed=3.0,
            rain=0.0,
            is_raining=0,
        )
        _, _, third_meta = default_plots(fresh=False, **params)
        self.assertFalse(third_meta['cache_hit'])


class PlotTimezoneTests(TestCase):
    def test_jd_array_to_local_dt_uses_berlin_wall_clock(self):
        from datetime import datetime as dt

        from bokeh.util.serialization import convert_datetime_type

        from .plots import (
            _plot_axis_label,
            _plot_axis_label_from_series,
            jd_array_to_local_dt,
        )

        # Noon UTC → 14:00 CEST in summer, 13:00 CET in winter
        summer_jd = Time('2024-07-01T12:00:00').jd
        winter_jd = Time('2024-01-15T12:00:00').jd
        summer_dt, winter_dt = jd_array_to_local_dt([summer_jd, winter_jd])

        self.assertIsNone(summer_dt.tzinfo)
        self.assertIsNone(winter_dt.tzinfo)
        self.assertEqual(summer_dt.hour, 14)
        self.assertEqual(winter_dt.hour, 13)
        self.assertEqual(_plot_axis_label(summer_dt), 'Time [CEST]')
        self.assertEqual(_plot_axis_label(winter_dt), 'Time [CET]')
        self.assertEqual(
            _plot_axis_label_from_series([winter_dt, summer_dt]),
            'Time [CET/CEST]',
        )

        # Bokeh encodes naive wall-clock as that clock time in UTC ms, so ticks
        # show local civil time (14:00 for summer, not 12:00 UTC).
        self.assertEqual(
            convert_datetime_type(summer_dt),
            convert_datetime_type(dt(2024, 7, 1, 14, 0)),
        )
        self.assertEqual(
            convert_datetime_type(winter_dt),
            convert_datetime_type(dt(2024, 1, 15, 13, 0)),
        )

    @override_settings(PLOT_DISPLAY_TIMEZONE='UTC')
    def test_plot_timezone_setting_utc(self):
        from .plots import _plot_axis_label, jd_array_to_local_dt

        summer_jd = Time('2024-07-01T12:00:00').jd
        summer_dt = jd_array_to_local_dt([summer_jd])[0]
        self.assertEqual(summer_dt.hour, 12)
        self.assertEqual(_plot_axis_label(summer_dt), 'Time [UTC]')

    @override_settings(PLOT_DISPLAY_TIMEZONE='America/New_York')
    def test_plot_timezone_setting_new_york(self):
        from .plots import _plot_axis_label, jd_array_to_local_dt

        # Noon UTC → 08:00 EDT in summer
        summer_jd = Time('2024-07-01T12:00:00').jd
        summer_dt = jd_array_to_local_dt([summer_jd])[0]
        self.assertEqual(summer_dt.hour, 8)
        self.assertEqual(_plot_axis_label(summer_dt), 'Time [EDT]')


class SecurityRemediationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.create_url = reverse('datasets-api:dataset-create')

    def _sample_payload(self, **overrides):
        payload = {
            'jd': Time.now().jd,
            'temperature': 12.5,
            'pressure': 1013.0,
            'humidity': 55.0,
            'illuminance': 1000.0,
            'wind_speed': 3.0,
            'sky_temp': 10.0,
            'box_temp': 15.0,
            'rain': 0.0,
            'is_raining': 0,
            'pm1_0': 8,
            'pm2_5': 12,
            'pm10': 18,
            'uv_index': 3,
        }
        payload.update(overrides)
        return payload

    def _provision_device(self, device_id='test-device', key_id='key1', secret=None):
        from django.utils import timezone as dj_tz

        from datasets.credentials import encrypt_secret
        from datasets.models import UploadDevice, UploadSigningKey

        if secret is None:
            secret = bytes.fromhex('00' * 32)
        user = User.objects.create_user(username=f'upload_{device_id}', password=None)
        user.set_unusable_password()
        user.save()
        device = UploadDevice.objects.create(
            device_id=device_id,
            label=device_id,
            service_user=user,
        )
        UploadSigningKey.objects.create(
            device=device,
            key_id=key_id,
            encrypted_secret=encrypt_secret(secret),
            valid_from=dj_tz.now(),
        )
        return device, secret

    def test_csv_formula_injection_neutralized(self):
        from datasets.csv_safe import sanitize_csv_cell

        self.assertTrue(sanitize_csv_cell('=1+1').startswith("'"))
        self.assertTrue(sanitize_csv_cell('  +cmd').startswith("'"))
        self.assertTrue(sanitize_csv_cell('@SUM(A1)').startswith("'"))
        self.assertEqual(sanitize_csv_cell('normal note'), 'normal note')

        Dataset.objects.create(**self._sample_payload(note='=CMD()'))
        response = self.client.get(reverse('datasets-api:download-csv'), {'dl': 'csv'})
        self.assertEqual(response.status_code, 200)
        body = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn("'=CMD()", body)

    def test_additional_plots_xss_payload_not_reflected(self):
        response = self.client.get(reverse('datasets-api:additional-plots'), {
            'plot_range': '<script>alert(1)</script>',
            'time_resolution': '300',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('<script>', str(response.data))
        self.assertEqual(response.data.get('code'), 'invalid_plot_params')

    def test_jd_rejects_nan_and_old(self):
        User.objects.create_user(username='data_upload_user', password='test-password')
        token = base64.b64encode(b'data_upload_user:test-password').decode('ascii')
        with override_settings(UPLOAD_AUTH_MODE='dual'):
            # form-urlencoded avoids JSON NaN encoding issues
            response = self.client.post(
                self.create_url,
                {'jd': 'nan', 'temperature': 12.5, 'pressure': 1013.0, 'humidity': 55.0,
                 'illuminance': 1000.0, 'wind_speed': 3.0, 'sky_temp': 10.0, 'box_temp': 15.0,
                 'rain': 0.0, 'is_raining': 0, 'pm1_0': 8, 'pm2_5': 12, 'pm10': 18, 'uv_index': 3},
                HTTP_AUTHORIZATION=f'Basic {token}',
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(
                self.create_url,
                self._sample_payload(jd=Time.now().jd - 2.0),
                format='json',
                HTTP_AUTHORIZATION=f'Basic {token}',
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_hmac_upload_and_idempotent_retry(self):
        import hashlib
        import hmac as hmac_mod
        import time as time_mod

        from datasets.hmac_client import build_canonical, encode_form

        device, secret = self._provision_device()
        payload = self._sample_payload()
        body = encode_form(payload)
        ts = str(int(time_mod.time()))
        nonce = 'aabbccddeeff00112233445566778899'
        canonical = build_canonical(
            device_id=device.device_id,
            key_id='key1',
            timestamp=ts,
            nonce=nonce,
            body=body,
        )
        signature = hmac_mod.new(secret, canonical.encode('utf-8'), hashlib.sha256).hexdigest()
        headers = {
            'HTTP_X_WEATHER_DEVICE': device.device_id,
            'HTTP_X_WEATHER_KEY_ID': 'key1',
            'HTTP_X_WEATHER_TIMESTAMP': ts,
            'HTTP_X_WEATHER_NONCE': nonce,
            'HTTP_X_WEATHER_SIGNATURE': signature,
        }
        with override_settings(UPLOAD_AUTH_MODE='hmac_only'):
            r1 = self.client.post(
                self.create_url,
                data=body,
                content_type='application/x-www-form-urlencoded',
                **headers,
            )
            r2 = self.client.post(
                self.create_url,
                data=body,
                content_type='application/x-www-form-urlencoded',
                **headers,
            )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(Dataset.objects.count(), 1)
        self.assertEqual(Dataset.objects.get().upload_device_id, device.pk)

    def test_hmac_rejects_body_tamper(self):
        device, secret = self._provision_device(device_id='tamper-dev', key_id='k2')
        from datasets.hmac_client import encode_form, build_canonical
        import hashlib
        import hmac as hmac_mod
        import time as time_mod

        payload = self._sample_payload()
        body = encode_form(payload)
        ts = str(int(time_mod.time()))
        nonce = '11223344556677889900aabbccddeeff'
        canonical = build_canonical(
            device_id=device.device_id,
            key_id='k2',
            timestamp=ts,
            nonce=nonce,
            body=body,
        )
        signature = hmac_mod.new(secret, canonical.encode('utf-8'), hashlib.sha256).hexdigest()
        tampered = body + b'&note=x'
        with override_settings(UPLOAD_AUTH_MODE='hmac_only'):
            response = self.client.post(
                self.create_url,
                data=tampered,
                content_type='application/x-www-form-urlencoded',
                HTTP_X_WEATHER_DEVICE=device.device_id,
                HTTP_X_WEATHER_KEY_ID='k2',
                HTTP_X_WEATHER_TIMESTAMP=ts,
                HTTP_X_WEATHER_NONCE=nonce,
                HTTP_X_WEATHER_SIGNATURE=signature,
            )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_hmac_only_rejects_basic(self):
        User.objects.create_user(username='data_upload_user', password='test-password')
        token = base64.b64encode(b'data_upload_user:test-password').decode('ascii')
        with override_settings(UPLOAD_AUTH_MODE='hmac_only'):
            response = self.client.post(
                self.create_url,
                self._sample_payload(),
                format='json',
                HTTP_AUTHORIZATION=f'Basic {token}',
            )
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_signing_helpers_stable(self):
        from datasets.api import signing

        body = b'jd=2460000.00000&temperature=20.00'
        digest = signing.body_sha256_hex(body)
        self.assertEqual(
            digest,
            '272add28edef85bb137dd1dec6f7c69d5a74f13f2032f00507465a8e564fb7f9',
        )
        canonical = signing.canonical_string(
            method='POST',
            path='/weather_station/weather_api/datasets/',
            content_type='application/x-www-form-urlencoded',
            device_id='test-device',
            key_id='key1',
            timestamp='1700000000',
            nonce='00112233445566778899aabbccddeeff',
            body_digest_hex=digest,
        )
        secret = bytes.fromhex('00' * 32)
        sig = signing.sign_canonical(secret, canonical)
        self.assertEqual(
            sig,
            '17dcbd5904c2dbf8a7780e2e90a8b63cb91fda199810fa18a24b1a3fb9a87c3c',
        )
        self.assertTrue(signing.verify_signature(secret, canonical, sig))
