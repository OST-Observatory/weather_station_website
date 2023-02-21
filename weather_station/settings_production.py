from pathlib import Path

from os.path import join

import environ

# Initialise environment variables
env = environ.Env()
environ.Env.read_env()

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': env("DATABASE_NAME"),
        'USER': env("DATABASE_USER"),
        'PASSWORD': env("DATABASE_PASSWORD"),
        'HOST': env("DATABASE_HOST"),
        'PORT': env("DATABASE_PORT"),
    }
}

FORCE_SCRIPT_NAME = '/weather_station'

# Logging
# https://docs.djangoproject.com/en/dev/topics/logging/#configuring-logging
# https://stackoverflow.com/questions/21943962/how-to-see-details-of-django-errors-with-gunicorn

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
            'datefmt': "%d/%b/%Y %H:%M:%S"
        },
    },
    'handlers': {
        'default': {
            'level': 'DEBUG',
            'class': 'logging.handlers.WatchedFileHandler',
            # 'class': 'logging.handlers.RotatingFileHandler',
            # 'maxBytes': 1024 * 1024 * 100,  # 100 mb
            'filename': join(
                BASE_DIR,
                env("LOG_DIR", default='/tmp/'),
                'not_django.log',
                ),
            'formatter': 'standard'
        },
        'django': {
            'level': 'DEBUG',
            'class': 'logging.handlers.WatchedFileHandler',
            # 'class': 'logging.handlers.RotatingFileHandler',
            # 'maxBytes': 1024 * 1024 * 100,  # 100 mb
            'filename': join(
                BASE_DIR,
                env("LOG_DIR", default='/tmp/'),
                'django.log',
                ),
            'formatter': 'standard'
        },
    },
    'loggers': {
        '': {
            'handlers': ['default'],
            'level': 'DEBUG',
            'propagate': True
        },
        'django': {
            'handlers': ['django'],
            'level': 'INFO',
            # 'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Email settings

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
