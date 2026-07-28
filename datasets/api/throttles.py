"""DRF throttle scopes for public and upload endpoints."""

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class DownloadRateThrottle(AnonRateThrottle):
    scope = 'downloads'


class PlotRateThrottle(AnonRateThrottle):
    scope = 'plots'


class UploadRateThrottle(SimpleRateThrottle):
    """Per-device (HMAC) or per-user (legacy Basic) upload rate limit."""

    scope = 'uploads'

    def get_cache_key(self, request, view):
        device = getattr(request, 'upload_device', None)
        if device is not None:
            ident = f'device:{device.device_id}'
        elif request.user and request.user.is_authenticated:
            ident = f'user:{request.user.pk}'
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class AuthFailureRateThrottle(SimpleRateThrottle):
    """Optional scope for authentication failure limiting at the view layer."""

    scope = 'auth_failures'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }
