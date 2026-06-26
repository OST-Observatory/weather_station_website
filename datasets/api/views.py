from email.utils import parsedate_to_datetime

import csv
import logging
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

import pytz
from astropy.time import Time
from django.conf import settings
from django.http import HttpResponseNotModified, StreamingHttpResponse
from django.utils import timezone
from django.utils.http import http_date
from django.views.decorators.cache import cache_page
from rest_framework import generics, permissions, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from datasets.forms import DateRangeForm, ParameterPlotForm
from datasets.models import Dataset
from datasets.plots import additional_plots_components

from .serializers import DatasetSerializer
from .throttles import DownloadRateThrottle

logger = logging.getLogger('weather.api')

MAX_JSON_DOWNLOAD_ROWS = 10_000

PLOT_QUERY_KEYS = frozenset({
    'plot_range',
    'time_resolution',
    'start_date',
    'end_date',
    'fresh',
})


def _plot_query_params(request):
    """Strip non-plot GET params (e.g. csrfmiddlewaretoken from dashboard form)."""
    query = request.GET.copy()
    for key in list(query.keys()):
        if key not in PLOT_QUERY_KEYS:
            del query[key]
    for key in ('start_date', 'end_date'):
        if key in query and not str(query.get(key, '')).strip():
            del query[key]
    return query


class CreateDatasetView(generics.CreateAPIView):
    """Authenticated POST-only endpoint for weather station data ingestion."""
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
def dataset_detail_not_allowed(request, pk=None):
    return Response(
        {'detail': 'Method not allowed.'},
        status=status.HTTP_405_METHOD_NOT_ALLOWED,
    )


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def additional_plots(request):
    form = ParameterPlotForm(_plot_query_params(request))
    if not form.is_valid():
        return Response({'errors': form.errors}, status=status.HTTP_400_BAD_REQUEST)

    bypass_key = getattr(settings, 'PLOT_CACHE_BYPASS_QUERY', 'fresh')
    fresh = request.GET.get(bypass_key) == '1'
    script, figures, plot_meta = additional_plots_components(
        fresh=fresh,
        **form.cleaned_data,
    )
    payload = {
        'script': script,
        'figures': figures,
        'cache_hit': plot_meta.get('cache_hit', False),
    }
    if figures.get('note'):
        payload['note'] = figures['note']
    return Response(payload)


@api_view(['GET'])
def get_last_dataset(request):
    dataset = (
        Dataset.objects
        .order_by('-added_on', '-jd', '-pk')
        .first()
    )
    if dataset is None:
        return Response(
            {'detail': 'No datasets available.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(DatasetSerializer(dataset).data)


def datetime_to_jd(dt):
    """Convert datetime or date to Julian Date."""
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time.min)

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)

    dt_utc = dt.astimezone(pytz.UTC)
    return Time(dt_utc).jd


def _download_error_response(exc):
    logger.exception('download_csv failed')
    message = 'Internal server error'
    if settings.DEBUG:
        message = str(exc)
    return Response(
        {'status': 'error', 'message': message},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@api_view(['GET'])
@throttle_classes([DownloadRateThrottle])
@cache_page(60)
def download_csv(request):
    """
    API endpoint to generate CSV data.
    Returns streamed CSV (preferred) or a limited JSON payload.
    """
    try:
        if request.GET.get('last_24h'):
            end_date = timezone.now()
            start_date = end_date - timedelta(hours=24)
            start_jd = datetime_to_jd(start_date)
            end_jd = datetime_to_jd(end_date)
        elif 'start_date' in request.GET and 'end_date' in request.GET:
            date_form = DateRangeForm(request.GET)
            if date_form.is_valid():
                start_date = date_form.cleaned_data['start_date']
                end_date = date_form.cleaned_data['end_date']
                end_date = datetime.combine(end_date, time.max)
                end_date = timezone.make_aware(end_date)
                start_jd = datetime_to_jd(start_date)
                end_jd = datetime_to_jd(end_date)
            else:
                return Response({
                    'status': 'error',
                    'errors': date_form.errors,
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            end_date = timezone.now()
            start_date = end_date - timedelta(days=1)
            start_jd = datetime_to_jd(start_date)
            end_jd = datetime_to_jd(end_date)

        start_time = datetime.now()
        qs = Dataset.objects.filter(jd__range=[start_jd, end_jd]).order_by('jd')

        latest = qs.order_by('-added_on').values('added_on').first()
        last_modified = latest['added_on'] if latest and latest['added_on'] else None

        etag = None
        if last_modified is not None:
            try:
                etag = (
                    f'W/"{int(start_jd * 1e6)}-{int(end_jd * 1e6)}'
                    f'-{int(last_modified.timestamp())}"'
                )
            except Exception:
                etag = None

        inm = request.META.get('HTTP_IF_NONE_MATCH')
        ims = request.META.get('HTTP_IF_MODIFIED_SINCE')
        if etag and inm and inm == etag:
            not_mod = HttpResponseNotModified()
            not_mod['ETag'] = etag
            if last_modified:
                not_mod['Last-Modified'] = http_date(last_modified.timestamp())
            return not_mod
        if last_modified and ims:
            try:
                ims_dt = parsedate_to_datetime(ims)
                if ims_dt.tzinfo is None:
                    ims_dt = ims_dt.replace(tzinfo=dt_timezone.utc)
                if last_modified <= ims_dt:
                    not_mod = HttpResponseNotModified()
                    if etag:
                        not_mod['ETag'] = etag
                    not_mod['Last-Modified'] = http_date(last_modified.timestamp())
                    return not_mod
            except Exception:
                pass

        wants_csv = (
            request.GET.get('dl') == 'csv'
            or 'text/csv' in request.META.get('HTTP_ACCEPT', '')
        )
        if wants_csv:
            field_names = [
                'pk', 'jd', 'temperature', 'sky_temp', 'box_temp',
                'pressure', 'humidity', 'illuminance', 'wind_speed',
                'rain', 'is_raining', 'pm1_0', 'pm2_5', 'pm10', 'uv_index',
                'note', 'merged', 'added_on', 'last_modified',
            ]

            class Echo:
                def write(self, value):
                    return value

            echo = Echo()
            writer = csv.writer(echo)

            def row_iter():
                yield writer.writerow(field_names)
                for row in qs.values_list(*field_names).iterator(chunk_size=2000):
                    normalized = []
                    for value in row:
                        if value is None:
                            normalized.append('')
                            continue
                        if isinstance(value, float):
                            if value != value or value in (float('inf'), float('-inf')):
                                normalized.append('')
                            else:
                                normalized.append(value)
                        else:
                            normalized.append(value)
                    yield writer.writerow(normalized)

            response = StreamingHttpResponse(row_iter(), content_type='text/csv')
            if request.GET.get('last_24h'):
                filename = 'weather_last24h.csv'
            elif 'start_date' in request.GET and 'end_date' in request.GET:
                filename = (
                    f"weather_{request.GET.get('start_date')}_"
                    f"{request.GET.get('end_date')}.csv"
                )
            else:
                filename = 'weather_data.csv'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Cache-Control'] = 'public, max-age=60'
            if etag:
                response['ETag'] = etag
            if last_modified:
                response['Last-Modified'] = http_date(last_modified.timestamp())
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(
                'download_csv csv range=[%s,%s] duration_ms=%.1f',
                start_jd, end_jd, duration_ms,
            )
            return response

        row_count = qs.count()
        if row_count > MAX_JSON_DOWNLOAD_ROWS:
            return Response({
                'status': 'error',
                'message': (
                    f'JSON export limited to {MAX_JSON_DOWNLOAD_ROWS} rows. '
                    'Use dl=csv for full export.'
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = DatasetSerializer(qs, many=True)
        resp = Response({'status': 'success', 'data': serializer.data})
        resp['Cache-Control'] = 'public, max-age=60'
        if etag:
            resp['ETag'] = etag
        if last_modified:
            resp['Last-Modified'] = http_date(last_modified.timestamp())
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(
            'download_csv json range=[%s,%s] rows=%s duration_ms=%.1f',
            start_jd, end_jd, len(serializer.data), duration_ms,
        )
        return resp

    except Exception as exc:
        return _download_error_response(exc)
