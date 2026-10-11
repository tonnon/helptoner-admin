from allauth.mfa import app_settings
from allauth.mfa.totp.internal.auth import TOTP
from django.core.cache import cache


def _marcar_codigo_usado(self, code: str) -> bool:
    """Guarda o código usado por toda a janela em que ele ainda seria aceito.

    Sobrescreve de propósito um método privado do allauth. Com MFA_TOTP_TOLERANCE = 1 um código
    vale por TOTP_PERIOD * (2 * TOTP_TOLERANCE + 1) segundos (90 s), mas o allauth só lembra dele
    por TOTP_PERIOD (30 s): um código usado cedo na janela poderia entrar de novo. A RFC 6238
    (§5.2) manda recusar o segundo uso. Devolve False se o código já foi usado.
    """
    janela = app_settings.TOTP_PERIOD * (2 * app_settings.TOTP_TOLERANCE + 1)
    return cache.add(self._get_used_cache_key(code), "y", timeout=janela)


def instalar():
    TOTP._mark_code_used = _marcar_codigo_usado
