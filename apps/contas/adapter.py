from allauth.account.adapter import DefaultAccountAdapter
from django.core.exceptions import ValidationError

from .sinais import registrar_acesso

MOTIVO_SENHA_ERRADA = "E-mail ou senha incorretos"
MOTIVO_BLOQUEIO = "Bloqueado por excesso de tentativas"


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

    def pre_authenticate(self, request, **credentials):
        try:
            super().pre_authenticate(request, **credentials)
        except ValidationError:  # limite de tentativas erradas estourado
            self._registrar_falha(request, credentials, MOTIVO_BLOQUEIO)
            raise

    def authentication_failed(self, request, **credentials):
        self._registrar_falha(request, credentials, MOTIVO_SENHA_ERRADA)

    def _registrar_falha(self, request, credentials, motivo):
        # A reautenticação (quem já entrou confirma a senha antes de uma ação) passa pelos
        # mesmos ganchos, mas não é login e fica fora do registro de acessos.
        if request.user.is_authenticated:
            return
        registrar_acesso(request, email=credentials.get("email", ""), sucesso=False, motivo=motivo)
