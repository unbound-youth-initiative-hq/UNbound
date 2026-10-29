"""Isolated test configuration: never reads a local .env or sends email."""
import os
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DJANGO_DEBUG'] = 'true'
os.environ['DJANGO_SECRET_KEY'] = 'isolated-test-key-not-for-production'
os.environ.pop('DATABASE_URL', None)
from .settings import *  # noqa: E402,F403
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
SECURE_SSL_REDIRECT = False
STORAGES['staticfiles'] = {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
