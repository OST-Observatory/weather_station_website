from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth import get_user_model
from django_otp.admin import OTPAdminSite

from .models import CalibrationEpoch, CloudBin, Dataset, UploadDevice, UploadSigningKey

# Require TOTP for Django admin logins (ADMIN_OTP_REQUIRED, default on).
if settings.ADMIN_OTP_REQUIRED:
    admin.site.__class__ = OTPAdminSite


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'jd', 'temperature', 'pressure', 'humidity', 'illuminance',
        'wind_speed', 'sky_temp', 'box_temp', 'rain', 'is_raining',
        'pm1_0', 'pm2_5', 'pm10', 'uv_index', 'upload_device', 'merged',
        'added_on', 'last_modified',
    )
    list_filter = (
        'merged', 'is_raining', 'upload_device', 'added_on', 'last_modified',
    )
    search_fields = (
        'note',
    )
    readonly_fields = ('added_on', 'last_modified', 'upload_device')
    date_hierarchy = 'added_on'


@admin.register(CalibrationEpoch)
class CalibrationEpochAdmin(admin.ModelAdmin):
    list_display = ('start', 'note', 'created_at')
    readonly_fields = ('created_at',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['start'].help_text = (
            'Time of the change at the sky sensors. Cloud detection ignores older data '
            'and shows "Calibrating" until 7 nights/days have been collected. '
            'Bins already computed after this time are re-classified by '
            '"manage.py update_cloud_status --recompute-days N".'
        )
        return form


@admin.register(CloudBin)
class CloudBinAdmin(admin.ModelAdmin):
    list_display = (
        'time', 'period', 'label', 'score', 'ir', 'lux', 'box', 'uv', 'sun_el',
        'calibration_periods', 'n_samples',
    )
    list_filter = ('label', 'period')
    date_hierarchy = 'time'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class UploadSigningKeyInline(admin.TabularInline):
    model = UploadSigningKey
    extra = 0
    readonly_fields = (
        'key_id', 'valid_from', 'valid_until', 'revoked_at', 'created_at',
    )
    exclude = ('encrypted_secret',)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(UploadDevice)
class UploadDeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'label', 'is_active', 'service_user', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('device_id', 'label')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [UploadSigningKeyInline]


@admin.register(UploadSigningKey)
class UploadSigningKeyAdmin(admin.ModelAdmin):
    list_display = (
        'key_id', 'device', 'valid_from', 'valid_until', 'revoked_at', 'created_at',
    )
    list_filter = ('device',)
    search_fields = ('key_id', 'device__device_id')
    readonly_fields = (
        'key_id', 'device', 'valid_from', 'valid_until', 'revoked_at', 'created_at',
    )
    exclude = ('encrypted_secret',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
