"""Registro de acessos: cada login, com ou sem sucesso, vira um RegistroAcesso.

O sucesso vem do sinal `user_logged_in` do Django e o código de verificação errado, do sinal do
allauth. A senha errada e o bloqueio por excesso de tentativas são gravados pelo
`apps.contas.adapter.ContaAdapter`.
"""

from allauth.account.adapter import get_adapter
from allauth.mfa.signals import authentication_failed
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import PermissionDenied
from django.dispatch import receiver

from .models import RegistroAcesso

MOTIVO_CODIGO_INVALIDO = "Código de verificação inválido"


def _ip(request) -> str | None:
    """O IP do cliente, lido do cabeçalho confiável da hospedagem (ver o allauth)."""
    try:
        return get_adapter(request).get_client_ip(request)
    except PermissionDenied:  # requisição sem IP, como a do force_login nos testes
        return None


def registrar_acesso(request, *, email: str, sucesso: bool, motivo: str = "", usuario=None):
    return RegistroAcesso.objects.create(
        email_tentado=(email or "")[:254],
        usuario=usuario,
        sucesso=sucesso,
        motivo=motivo,
        ip=_ip(request),
        navegador=request.META.get("HTTP_USER_AGENT", "")[:300],
    )


@receiver(user_logged_in, dispatch_uid="contas_registrar_login")
def registrar_login(sender, request, user, **kwargs):
    registrar_acesso(request, email=user.email, sucesso=True, usuario=user)


@receiver(authentication_failed, dispatch_uid="contas_registrar_codigo_invalido")
def registrar_codigo_invalido(sender, request, user, reauthentication=False, **kwargs):
    if reauthentication:  # quem já entrou e erra o código ao confirmar uma ação não é login
        return
    registrar_acesso(
        request, email=user.email, sucesso=False, motivo=MOTIVO_CODIGO_INVALIDO, usuario=user
    )
