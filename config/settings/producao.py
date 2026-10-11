import os
import warnings

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured

from apps.core.sentry import limpar_evento

from .base import *  # noqa: F403

DEBUG = False

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY.")

# A Vercel define estas variáveis em cada implantação (produção, ramo e endereço da versão).
_hosts = [
    os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", ""),
    os.environ.get("VERCEL_BRANCH_URL", ""),
    os.environ.get("VERCEL_URL", ""),
    *os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(","),
]
ALLOWED_HOSTS = list(dict.fromkeys(h.strip() for h in _hosts if h.strip()))
CSRF_TRUSTED_ORIGINS = ["https://" + h for h in ALLOWED_HOSTS]

DATABASES = {
    "default": banco_de_dados(  # noqa: F405
        os.environ["DATABASE_URL"],
        conn_max_age=0,
        ssl_require=True,
        disable_server_side_cursors=True,
    )
}
# O pooler do Neon (PgBouncer) roda em modo transação: sem comandos preparados no servidor.
DATABASES["default"]["OPTIONS"]["prepare_threshold"] = None

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Atrás da Vercel o IP do cliente vem neste cabeçalho (limite de tentativas do allauth). No plano B
# (Render), CABECALHO_IP_CLIENTE troca o cabeçalho; vazio usa o REMOTE_ADDR do Django.
ALLAUTH_TRUSTED_CLIENT_IP_HEADER = (
    os.environ.get("CABECALHO_IP_CLIENTE", "x-vercel-forwarded-for") or None
)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Na Vercel, os arquivos estáticos saem da CDN, depois do collectstatic automático do build; a
# pasta staticfiles/ pode não existir na função, e o WhiteNoise avisaria "No directory at". O aviso
# é atribuído a django.core.handlers (stacklevel=3), por isso o filtro não limita o módulo.
warnings.filterwarnings("ignore", message="No directory at")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simples": {"format": "%(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simples"}},
    "loggers": {
        "helptoner": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        environment=os.environ.get("VERCEL_ENV", "producao"),
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=0.0,
        before_send=limpar_evento,
    )
