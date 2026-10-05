from allauth.account.adapter import DefaultAccountAdapter
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import Usuario
from .sinais import registrar_acesso

MOTIVO_SENHA_ERRADA = "E-mail ou senha incorretos"
MOTIVO_BLOQUEIO = "Bloqueado por excesso de tentativas"
MOTIVO_DESATIVADO = "Acesso desativado"


class ContaAdapter(DefaultAccountAdapter):
    """Ajustes do allauth: sem cadastro público e com as tentativas erradas registradas."""

    error_messages = {
        **DefaultAccountAdapter.error_messages,
        "email_password_mismatch": "E-mail ou senha incorretos.",
        "too_many_login_attempts": (
            "Muitas tentativas erradas. Por segurança, o acesso ficou bloqueado por alguns "
            "minutos. Tente de novo mais tarde."
        ),
    }

    def is_open_for_signup(self, request):
        return False

    def get_password_change_redirect_url(self, request):
        return reverse("contas:minha_conta")

    def _get_login_attempts_cache_key(self, request, **credentials):
        """Chave do limite de tentativas erradas por conta: só o e-mail.

        Sobrescreve de propósito um método privado do allauth. Sem o django.contrib.sites, o
        allauth monta a chave com request.get_host(), e o Django aceita o mesmo site escrito de
        jeitos diferentes ("HELPTONER.com.br", "helptoner.com.br:443"): cada jeito seria uma
        conta nova de tentativas, e o bloqueio da conta poderia ser contornado.
        """
        email = credentials.get("email", credentials.get("username", ""))
        return f"login:{email.strip().lower()}"

    def pre_authenticate(self, request, **credentials):
        try:
            super().pre_authenticate(request, **credentials)
        except ValidationError:  # limite de tentativas erradas estourado
            self._registrar_falha(request, credentials.get("email", ""), MOTIVO_BLOQUEIO)
            raise

    def authentication_failed(self, request, **credentials):
        # A tela continua com o mesmo "E-mail ou senha incorretos."; só o registro diz que o
        # e-mail é de um acesso desativado.
        email = credentials.get("email", "")
        desativado = Usuario.objects.filter(email=email.strip().lower(), is_active=False).first()
        if desativado:
            self._registrar_falha(request, email, MOTIVO_DESATIVADO, usuario=desativado)
        else:
            self._registrar_falha(request, email, MOTIVO_SENHA_ERRADA)

    def respond_user_inactive(self, request, user):
        # Senha certa, mas acesso desativado: o allauth mostra a tela "Acesso desativado".
        self._registrar_falha(request, user.email, MOTIVO_DESATIVADO, usuario=user)
        return super().respond_user_inactive(request, user)

    def _registrar_falha(self, request, email, motivo, usuario=None):
        # A reautenticação (quem já entrou confirma a senha antes de uma ação) passa pelos
        # mesmos ganchos, mas não é login e fica fora do registro de acessos.
        if request.user.is_authenticated:
            return
        registrar_acesso(request, email=email, sucesso=False, motivo=motivo, usuario=usuario)
