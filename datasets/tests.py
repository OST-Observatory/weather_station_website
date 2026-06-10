import base64
from datetime import date, timedelta
from unittest.mock import patch

from astropy.time import Time
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Dataset


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
    @patch('datasets.views.Observer')
    def test_dashboard_no_data(self, mock_observer_cls):
        observer = mock_observer_cls.return_value
        observer.sun_rise_time.return_value = Time('2026-04-16 04:30:00')
        observer.sun_set_time.return_value = Time('2026-04-16 20:15:00')

        response = Client().get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clear')
        self.assertContains(response, 'wi-day-sunny')
