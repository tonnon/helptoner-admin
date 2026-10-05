import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY.")

_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]

DATABASES = {
    "default": banco_de_dados(  # noqa: F405
        os.environ["DATABASE_URL"],
        conn_max_age=0,
        ssl_require=True,
        disable_server_side_cursors=True,
    )
}

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
