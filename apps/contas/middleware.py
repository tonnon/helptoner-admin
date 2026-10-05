"""Primeiro acesso obrigatório: nova senha → aplicativo autenticador → códigos de recuperação.

Enquanto não termina, o usuário logado só chega às rotas da etapa em que está (e a sair e
confirmar a senha, que o allauth pede antes de ativar o autenticador ou mostrar os códigos).
"""

from allauth.mfa.models import Authenticator
from django.urls import reverse

from apps.core.htmx import redirecionar

ETAPA_SENHA = 1
ETAPA_AUTENTICADOR = 2
ETAPA_CODIGOS = 3

# Rotas liberadas em cada etapa; a primeira é para onde as outras levam.
ROTAS_DA_ETAPA = {
    ETAPA_SENHA: ("contas:primeiro_acesso_senha",),
    ETAPA_AUTENTICADOR: ("mfa_activate_totp",),
    ETAPA_CODIGOS: (
        "mfa_view_recovery_codes",
        "mfa_download_recovery_codes",
        "contas:primeiro_acesso_concluir",
    ),
}

# Liberadas em qualquer etapa. As rotas sem login (core:saude, o login...) nem chegam a ser
# conferidas: veja PrimeiroAcessoMiddleware.process_view.
ROTAS_DE_TODAS_AS_ETAPAS = frozenset(
    {"account_logout", "account_reauthenticate", "mfa_reauthenticate"}
)


def tem_autenticador(usuario) -> bool:
    """O usuário tem o aplicativo autenticador (TOTP) ativo."""
    return Authenticator.objects.filter(user=usuario, type=Authenticator.Type.TOTP).exists()


def etapa_do_primeiro_acesso(usuario) -> int | None:
    """A etapa em que o usuário está, ou None se ele já concluiu o primeiro acesso.

    Só consulta o banco quando os códigos de recuperação ainda não foram entregues.
    """
    if usuario.deve_trocar_senha:
        return ETAPA_SENHA
    if usuario.codigos_recuperacao_entregues:
        return None
    return ETAPA_CODIGOS if tem_autenticador(usuario) else ETAPA_AUTENTICADOR


class PrimeiroAcessoMiddleware:
    """Leva quem não terminou o primeiro acesso de volta à etapa atual (HX-Redirect no HTMX)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Rotas sem login passam sem olhar o usuário: a de saúde não pode tocar na sessão nem
        # no banco, e as outras (login, rotas desligadas...) já são abertas a qualquer um.
        if not getattr(view_func, "login_required", True):
            return None
        usuario = request.user
        if not usuario.is_authenticated:  # o LoginObrigatorioMiddleware cuida disso
            return None
        etapa = etapa_do_primeiro_acesso(usuario)
        if etapa is None:
            return None
        rotas = ROTAS_DA_ETAPA[etapa]
        rota = request.resolver_match.view_name
        if rota in rotas or rota in ROTAS_DE_TODAS_AS_ETAPAS:
            return None
        return redirecionar(request, reverse(rotas[0]))
