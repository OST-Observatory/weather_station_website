# from django.contrib.auth.models import User, Group
# from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
# , SerializerMethodField

from datasets.models import dataset

class DatasetSerializer(ModelSerializer):
    class Meta:
        model = dataset
        fields = [
            'pk',
            'jd',
            'temperature',
            'pressure',
            'humidity',
            'illuminance',
            'wind_speed',
            ]
        read_only_fields = ('pk',)
