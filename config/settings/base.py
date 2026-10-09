import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
    "simple_history",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "apps.core",
    "apps.contas",
    "apps.cadastros",
    "apps.estoque",
    "apps.pedidos",
    "apps.relatorios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Caractere nulo no GET ou no POST: 400 antes de tudo, sem sessão e sem banco (Ruling R25).
    "apps.core.middleware.RecusarNuloMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.LoginObrigatorioMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.contas.middleware.PrimeiroAcessoMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.contexto.navegacao",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

AUTH_USER_MODEL = "contas.Usuario"
AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "nome")},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


def banco_de_dados(url: str, **opcoes) -> dict:
    """Monta a configuração de um banco a partir de uma URL."""
    return dj_database_url.parse(url, **opcoes)


LOGIN_URL = "/contas/login/"
LOGIN_REDIRECT_URL = "/"
CSRF_FAILURE_VIEW = "apps.core.views.falha_csrf"

SESSION_COOKIE_AGE = 7200
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_django",
    }
}

# Login pelo django-allauth: e-mail e senha, sem cadastro público, e verificação em duas etapas
# (TOTP e códigos de recuperação). As tentativas erradas contam no cache acima, no PostgreSQL.
ACCOUNT_ADAPTER = "apps.contas.adapter.ContaAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_SESSION_REMEMBER = False
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = False
ACCOUNT_FORMS = {"change_password": "apps.contas.forms.TrocarSenhaForm"}
ACCOUNT_RATE_LIMITS = {"login": "30/m/ip", "login_failed": "10/m/ip,5/5m/key"}
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "Helptoner Pedidos"
MFA_RECOVERY_CODE_COUNT = 10
# O sistema não verifica e-mails (quem cadastra é o Administrador) e não cria EmailAddress do
# allauth. Se um aparecer não verificado (pelo painel, por exemplo), o allauth recusaria ativar o
# autenticador e o primeiro acesso ficaria num laço entre a ativação e a tela do 2FA.
MFA_ALLOW_UNVERIFIED_EMAIL = True
ALLAUTH_TRUSTED_CLIENT_IP_HEADER = None  # em produção: "x-vercel-forwarded-for" (Tarefa 28)


def normalizar_admin_url(valor: str) -> str:
    """O caminho do painel com uma barra só, no fim ("/segredo" → "segredo/").

    Recusa o vazio (o painel ocuparia a raiz do site) e o padrão "admin".
    """
    caminho = valor.strip().strip("/")
    if not caminho or caminho.lower() == "admin":
        raise ImproperlyConfigured(
            'ADMIN_URL precisa ser um caminho não padrão, como "manutencao/" (nem vazio, nem '
            '"admin").'
        )
    return f"{caminho}/"


# Painel de manutenção do Django (só o superusuário), num endereço que não é o padrão /admin/.
ADMIN_URL = normalizar_admin_url(os.environ.get("ADMIN_URL", "manutencao/"))
