import os

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

if os.environ.get("VERCEL"):
    raise ImproperlyConfigured(
        "config.settings.local não pode rodar na Vercel; "
        "defina DJANGO_SETTINGS_MODULE=config.settings.producao."
    )

from .base import *  # noqa: E402, F403

load_dotenv(BASE_DIR / ".env.local")  # noqa: F405

DEBUG = True
SECRET_KEY = "chave-fixa-apenas-para-desenvolvimento"  # noqa: S105
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
DATABASES = {"default": banco_de_dados(os.environ["DATABASE_URL"])}  # noqa: F405
