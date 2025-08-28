from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime, timedelta, date, time
from astropy.time import Time
import pytz
import csv
from django.http import StreamingHttpResponse, HttpResponseNotModified
from django.utils.http import http_date
from django.utils.dateparse import parse_datetime
import logging
from django.views.decorators.cache import cache_page

from datasets.models import Dataset
from datasets.forms import DateRangeForm
from .serializers import DatasetSerializer


class DatasetViewSet(viewsets.ModelViewSet):
    """
        API endpoint that allows datasets to be viewed or edited.
    """
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(['GET'])
def get_last_dataset(request):
    dataset = Dataset.objects.latest("added_on")

    return Response(DatasetSerializer(dataset).data)

def datetime_to_jd(dt):
    """Convert datetime or date to Julian Date."""
    # Convert date to datetime if necessary
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time.min)
    
    # Ensure datetime is timezone-aware
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    # Convert to UTC
    dt_utc = dt.astimezone(pytz.UTC)
    # Convert to Julian Date
    t = Time(dt_utc)
    return t.jd

@api_view(['GET'])
@cache_page(60)
def download_csv(request):
    """
    API endpoint to generate CSV data.
    Returns either CSV data or error messages.
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
                # Set end_date to end of day (23:59:59)
                end_date = datetime.combine(end_date, time.max)
                end_date = timezone.make_aware(end_date)
                start_jd = datetime_to_jd(start_date)
                end_jd = datetime_to_jd(end_date)
            else:
                return Response({
                    'status': 'error',
                    'errors': date_form.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Default to last 24 hours
            end_date = timezone.now()
            start_date = end_date - timedelta(days=1)
            start_jd = datetime_to_jd(start_date)
            end_jd = datetime_to_jd(end_date)

        start_time = datetime.now()
        qs = Dataset.objects.filter(jd__range=[start_jd, end_jd]).order_by('jd')

        # ETag / Last-Modified based on newest record in range
        latest = qs.order_by('-added_on').values('added_on').first()
        if latest and latest['added_on']:
            last_modified = latest['added_on']
        else:
            last_modified = None

        # Build a weak ETag based on range and last_modified
        etag = None
        if last_modified is not None:
            try:
                etag = f"W/\"{int(start_jd*1e6)}-{int(end_jd*1e6)}-{int(last_modified.timestamp())}\""
            except Exception:
                etag = None

        # Conditional request handling (If-None-Match / If-Modified-Since)
        inm = request.META.get('HTTP_IF_NONE_MATCH')
        ims = request.META.get('HTTP_IF_MODIFIED_SINCE')
        if etag and inm and inm == etag:
            not_mod = HttpResponseNotModified()
            not_mod['ETag'] = etag
            if last_modified:
                not_mod['Last-Modified'] = http_date(last_modified.timestamp())
            return not_mod
        if last_modified and ims:
            # Parse If-Modified-Since and compare
            try:
                # Some clients send RFC1123 dates; http_date parsing is one-way, so fall back to timestamp compare below
                from email.utils import parsedate_to_datetime
                ims_dt = parsedate_to_datetime(ims)
                if ims_dt.tzinfo is None:
                    from datetime import timezone as _tz
                    ims_dt = ims_dt.replace(tzinfo=_tz.utc)
                if last_modified <= ims_dt:
                    not_mod = HttpResponseNotModified()
                    if etag:
                        not_mod['ETag'] = etag
                    not_mod['Last-Modified'] = http_date(last_modified.timestamp())
                    return not_mod
            except Exception:
                pass

        # If client requests CSV (via query param 'dl=csv' or Accept header), stream CSV
        wants_csv = request.GET.get('dl') == 'csv' or 'text/csv' in request.META.get('HTTP_ACCEPT', '')
        if wants_csv:
            # Prepare streaming CSV response
            field_names = [
                'pk', 'jd', 'temperature', 'sky_temp', 'box_temp',
                'pressure', 'humidity', 'illuminance', 'wind_speed',
                'rain', 'is_raining', 'co2_ppm', 'tvoc_ppb',
                'note', 'merged', 'added_on', 'last_modified'
            ]

            class Echo:
                def write(self, value):
                    return value

            echo = Echo()
            writer = csv.writer(echo)

            def row_iter():
                # Header
                yield writer.writerow(field_names)
                for row in qs.values_list(*field_names).iterator(chunk_size=2000):
                    # Normalize None/NaN/Inf -> empty string or numeric
                    normalized = []
                    for value in row:
                        if value is None:
                            normalized.append('')
                            continue
                        if isinstance(value, float):
                            if value != value or value in (float('inf'), float('-inf')):  # NaN/Inf
                                normalized.append('')
                            else:
                                normalized.append(value)
                        else:
                            normalized.append(value)
                    yield writer.writerow(normalized)

            response = StreamingHttpResponse(row_iter(), content_type='text/csv')
            # Dynamic filename
            if request.GET.get('last_24h'):
                filename = 'weather_last24h.csv'
            elif 'start_date' in request.GET and 'end_date' in request.GET:
                filename = f"weather_{request.GET.get('start_date')}_{request.GET.get('end_date')}.csv"
            else:
                filename = 'weather_data.csv'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Cache-Control'] = 'public, max-age=60'
            if etag:
                response['ETag'] = etag
            if last_modified:
                response['Last-Modified'] = http_date(last_modified.timestamp())
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            logging.getLogger('weather.api').info('download_csv csv range=[%s,%s] rows=%s duration_ms=%.1f', start_jd, end_jd, qs.count(), duration_ms)
            return response

        # Default JSON response (legacy behavior)
        serializer = DatasetSerializer(qs, many=True)
        resp = Response({'status': 'success', 'data': serializer.data})
        resp['Cache-Control'] = 'public, max-age=60'
        if etag:
            resp['ETag'] = etag
        if last_modified:
            resp['Last-Modified'] = http_date(last_modified.timestamp())
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        logging.getLogger('weather.api').info('download_csv json range=[%s,%s] rows=%s duration_ms=%.1f', start_jd, end_jd, len(serializer.data), duration_ms)
        return resp
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)