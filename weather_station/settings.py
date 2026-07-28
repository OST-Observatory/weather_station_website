"""
Django settings for weather_station project.
"""

from pathlib import Path

import os

import environ
from django.core.exceptions import ImproperlyConfigured

# Initialise environment variables
env = environ.Env()
environ.Env.read_env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# Application definition

INSTALLED_APPS = [
    'datasets.apps.DatasetsConfig',
    'rest_framework',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'axes',
]

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'axes.middleware.AxesMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'datasets.middleware.DashboardRateLimitMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Security headers (can be tuned in production settings)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

from django.utils.csp import CSP

# CSP (Django 6) — report-only until browser smoke tests pass, then move policy to SECURE_CSP.
SECURE_CSP = {}
SECURE_CSP_REPORT_ONLY = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF, CSP.NONCE],
    'style-src': [CSP.SELF, CSP.UNSAFE_INLINE],
    'img-src': [CSP.SELF, 'data:'],
    'font-src': [CSP.SELF, 'data:'],
    'connect-src': [CSP.SELF],
    'object-src': [CSP.NONE],
    'base-uri': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
}

ROOT_URLCONF = 'weather_station.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.csp',
            ],
        },
    },
]

WSGI_APPLICATION = 'weather_station.wsgi.application'

# Django rest API framework
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/min',
        'downloads': '30/min',
        'plots': '60/min',
        'uploads': '240/min',
        'auth_failures': '20/min',
    },
    # Exactly one trusted reverse-proxy hop (Apache).
    'NUM_PROXIES': 1,
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATICFILES_DIRS = ['site_static', ]

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static/')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Dashboard plot cache
PLOT_CACHE_MIN_RESOLUTION_SECONDS = 60
PLOT_CACHE_LIVE_MAX_DAYS = 1.0
PLOT_CACHE_TTL_SECONDS = 30
PLOT_CACHE_BYPASS_QUERY = 'fresh'

PLOT_PG_BIN_MIN_DAYS = 1.0

PLOT_DISPLAY_TIMEZONE = env('PLOT_DISPLAY_TIMEZONE', default='Europe/Berlin')

# Upload authentication
UPLOAD_AUTH_MODE = env('UPLOAD_AUTH_MODE', default='dual')  # dual | hmac_only
UPLOAD_LEGACY_BASIC_USERNAME = env('UPLOAD_LEGACY_BASIC_USERNAME', default='data_upload_user')
UPLOAD_HMAC_CANONICAL_PATH = env(
    'UPLOAD_HMAC_CANONICAL_PATH',
    default='/weather_station/weather_api/datasets/',
)
UPLOAD_HMAC_TIMESTAMP_SKEW_SECONDS = env.int('UPLOAD_HMAC_TIMESTAMP_SKEW_SECONDS', default=300)
UPLOAD_HMAC_REPLAY_TTL_SECONDS = env.int('UPLOAD_HMAC_REPLAY_TTL_SECONDS', default=600)
UPLOAD_REPLAY_CACHE_ALIAS = env('UPLOAD_REPLAY_CACHE_ALIAS', default='default')
UPLOAD_JD_MAX_AGE_DAYS = env.float('UPLOAD_JD_MAX_AGE_DAYS', default=1.0)
UPLOAD_JD_MAX_FUTURE_DAYS = env.float(
    'UPLOAD_JD_MAX_FUTURE_DAYS',
    default=5.0 / (24.0 * 60.0),
)
UPLOAD_CREDENTIAL_MASTER_KEY = env('UPLOAD_CREDENTIAL_MASTER_KEY', default='')

DASHBOARD_RATE_LIMIT_ENABLED = env.bool('DASHBOARD_RATE_LIMIT_ENABLED', default=True)
DASHBOARD_RATE_LIMIT_PER_MINUTE = env.int('DASHBOARD_RATE_LIMIT_PER_MINUTE', default=60)

# django-axes
AXES_FAILURE_LIMIT = env.int('AXES_FAILURE_LIMIT', default=5)
AXES_COOLOFF_TIME = env.float('AXES_COOLOFF_TIME', default=1.0)  # hours
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]

# Default cache (overridden in production with Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'weather-dev-cache',
    }
}

# Fail-fast environment selection — no DEVICE/hostname fallback.
_django_env = env('DJANGO_ENV', default='').strip().lower()
if _django_env not in ('development', 'production'):
    raise ImproperlyConfigured(
        "DJANGO_ENV must be set to 'development' or 'production' "
        f"(got {_django_env!r})"
    )
DJANGO_ENV = _django_env

if DJANGO_ENV == 'production':
    from .settings_production import (
        DEBUG,
        ALLOWED_HOSTS,
        DATABASES,
        LOGGING,
        DEFAULT_FROM_EMAIL,
        FORCE_SCRIPT_NAME,
        CSRF_TRUSTED_ORIGINS,
        SECURE_PROXY_SSL_HEADER,
        SECURE_SSL_REDIRECT,
        SESSION_COOKIE_SECURE,
        CSRF_COOKIE_SECURE,
        SECURE_HSTS_SECONDS,
        SECURE_HSTS_INCLUDE_SUBDOMAINS,
        SECURE_HSTS_PRELOAD,
        CACHES,
    )
else:
    from .settings_development import DEBUG, ALLOWED_HOSTS, DATABASES, LOGGING
    # Stable local-only Fernet key so encrypted secrets survive process reloads.
    if not UPLOAD_CREDENTIAL_MASTER_KEY:
        import base64
        import hashlib

        digest = hashlib.sha256(f'upload-master:{SECRET_KEY}'.encode('utf-8')).digest()
        UPLOAD_CREDENTIAL_MASTER_KEY = base64.urlsafe_b64encode(digest).decode('ascii')
