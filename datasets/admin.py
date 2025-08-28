from django.contrib import admin
from .models import Dataset


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'jd', 'temperature', 'pressure', 'humidity', 'illuminance',
        'wind_speed', 'sky_temp', 'box_temp', 'rain', 'is_raining',
        'co2_ppm', 'tvoc_ppb', 'merged', 'added_on', 'last_modified'
    )
    list_filter = (
        'merged', 'is_raining', 'added_on', 'last_modified'
    )
    search_fields = (
        'note',
    )
    readonly_fields = ('added_on', 'last_modified')
    date_hierarchy = 'added_on'
