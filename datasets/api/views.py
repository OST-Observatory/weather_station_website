from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime, timedelta, date, time
from astropy.time import Time
import pytz

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

        data = Dataset.objects.filter(jd__range=[start_jd, end_jd]).order_by('jd')
        serializer = DatasetSerializer(data, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        })
        
    except Exception as e:
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)