from rest_framework import serializers
from datasets.models import Dataset
import numpy as np


class DatasetSerializer(serializers.ModelSerializer):
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
            'note',
            'merged',
            'added_on',
            'last_modified',
            ]
        read_only_fields = ('pk',)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Convert NaN values to None (which becomes null in JSON)
        for key, value in data.items():
            if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
                data[key] = None
        return data
