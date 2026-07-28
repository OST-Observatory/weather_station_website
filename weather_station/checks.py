from django.conf import settings
from django.core.checks import Error, register


@register()
def weather_deploy_checks(app_configs, **kwargs):
    errors = []
    if getattr(settings, 'DJANGO_ENV', None) != 'production':
        return errors

    if settings.DEBUG:
        errors.append(Error(
            'DEBUG must be False in production',
            id='weather.E001',
        ))
    cache_backend = settings.CACHES.get('default', {}).get('BACKEND', '')
    if 'redis' not in cache_backend.lower():
        errors.append(Error(
            'Production cache backend must be Redis',
            id='weather.E002',
        ))
    if not getattr(settings, 'SESSION_COOKIE_SECURE', False):
        errors.append(Error(
            'SESSION_COOKIE_SECURE must be True in production',
            id='weather.E003',
        ))
    if not getattr(settings, 'CSRF_COOKIE_SECURE', False):
        errors.append(Error(
            'CSRF_COOKIE_SECURE must be True in production',
            id='weather.E004',
        ))
    if not getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
        errors.append(Error(
            'SECURE_PROXY_SSL_HEADER must be configured behind Apache TLS',
            id='weather.E005',
        ))
    if not getattr(settings, 'UPLOAD_CREDENTIAL_MASTER_KEY', ''):
        errors.append(Error(
            'UPLOAD_CREDENTIAL_MASTER_KEY is required in production',
            id='weather.E006',
        ))
    mode = getattr(settings, 'UPLOAD_AUTH_MODE', '')
    if mode not in ('dual', 'hmac_only'):
        errors.append(Error(
            "UPLOAD_AUTH_MODE must be 'dual' or 'hmac_only'",
            id='weather.E007',
        ))
    return errors
