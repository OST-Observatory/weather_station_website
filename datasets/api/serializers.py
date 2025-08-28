from rest_framework import serializers
from datasets.models import Dataset
import numpy as np


class DatasetSerializer(serializers.ModelSerializer):
    def _clamp_and_validate(self, value, min_value, max_value, field_name):
        if value is None:
            return value
        try:
            numeric = float(value)
        except Exception:
            raise serializers.ValidationError({field_name: f"{field_name} must be a number"})
        if numeric < min_value or numeric > max_value:
            raise serializers.ValidationError({field_name: f"{field_name} must be between {min_value} and {max_value}"})
        return numeric

    def validate_temperature(self, value):
        return self._clamp_and_validate(value, -50.0, 60.0, 'temperature')

    def validate_sky_temp(self, value):
        return self._clamp_and_validate(value, -100.0, 60.0, 'sky_temp')

    def validate_box_temp(self, value):
        return self._clamp_and_validate(value, -40.0, 80.0, 'box_temp')

    def validate_pressure(self, value):
        return self._clamp_and_validate(value, 870.0, 1100.0, 'pressure')

    def validate_humidity(self, value):
        return self._clamp_and_validate(value, 0.0, 100.0, 'humidity')

    def validate_illuminance(self, value):
        return self._clamp_and_validate(value, 0.0, 200000.0, 'illuminance')

    def validate_wind_speed(self, value):
        return self._clamp_and_validate(value, 0.0, 60.0, 'wind_speed')

    def validate_rain(self, value):
        return self._clamp_and_validate(value, 0.0, 1e6, 'rain')

    def validate_co2_ppm(self, value):
        # Accept ints/floats, convert to int
        numeric = self._clamp_and_validate(value, 0.0, 5000.0, 'co2_ppm')
        return int(round(numeric))

    def validate_tvoc_ppb(self, value):
        numeric = self._clamp_and_validate(value, 0.0, 10000.0, 'tvoc_ppb')
        return int(round(numeric))

    def validate_is_raining(self, value):
        # Allow truthy strings/numbers, coerce to 0/1
        try:
            ivalue = int(round(float(value)))
        except Exception:
            raise serializers.ValidationError({"is_raining": "is_raining must be 0 or 1"})
        if ivalue not in (0, 1):
            raise serializers.ValidationError({"is_raining": "is_raining must be 0 or 1"})
        return ivalue

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
            'sky_temp',
            'box_temp',
            'rain',
            'is_raining',
            'co2_ppm',
            'tvoc_ppb',
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
