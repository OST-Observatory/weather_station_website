from rest_framework.serializers import ModelSerializer

from datasets.models import Dataset


class DatasetSerializer(ModelSerializer):
    class Meta:
        model = Dataset
        fields = [
            'pk',
            'jd',
            'temperature',
            'pressure',
            'humidity',
            'illuminance',
            'wind_speed',
            'rain',
            ]
        read_only_fields = ('pk',)
