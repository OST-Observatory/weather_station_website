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
            'co2_ppm': 420,
            'tvoc_ppb': 50,
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
    def test_dashboard_fresh_query_bypass(self, mock_observer_cls):
        observer = mock_observer_cls.return_value
        observer.sun_rise_time.return_value = Time('2026-04-16 04:30:00')
        observer.sun_set_time.return_value = Time('2026-04-16 20:15:00')

        params = {
            'plot_range': '0.5',
            'time_resolution': '300',
        }
        with patch('datasets.views.default_plots', wraps=default_plots) as mocked:
            Client().get(reverse('dashboard'), {**params, 'fresh': '1'})
            Client().get(reverse('dashboard'), params)
            self.assertEqual(mocked.call_count, 2)
            self.assertTrue(mocked.call_args_list[0].kwargs.get('fresh'))

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
            co2_ppm=420,
            tvoc_ppb=50,
        )
        response = APIClient().get(reverse('datasets-api:additional-plots'), {
            'plot_range': '0.5',
            'time_resolution': '300',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('script', response.data)
        self.assertIn('figures', response.data)
        self.assertIn('temp_combined', response.data['figures'])


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
