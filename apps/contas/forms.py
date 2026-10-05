from allauth.account.forms import ChangePasswordForm
from django.contrib.auth.forms import SetPasswordForm

# No lugar da lista de regras do Django (um <ul>), que não cabe na ajuda de um campo.
AJUDA_NOVA_SENHA = (
    "Pelo menos 12 caracteres. Não use senha comum, só números nem algo parecido com seu "
    "nome ou e-mail."
)


def _ajustar_campos(form, rotulos: dict[str, str]) -> None:
    """Rótulos do sistema, sem placeholder (o rótulo já fica visível acima do campo)."""
    for nome, rotulo in rotulos.items():
        form.fields[nome].label = rotulo
        form.fields[nome].widget.attrs.pop("placeholder", None)


class NovaSenhaForm(SetPasswordForm):
    """Etapa 1 do primeiro acesso: troca a senha temporária, que não pode ser repetida."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        _ajustar_campos(
            self, {"new_password1": "Nova senha", "new_password2": "Confirme a nova senha"}
        )
        self.fields["new_password1"].help_text = AJUDA_NOVA_SENHA
        self.fields["new_password2"].help_text = ""

    def clean(self):
        nova = self.cleaned_data.get("new_password1")
        if nova and self.user.check_password(nova):
            self.add_error(
                "new_password1", "A nova senha precisa ser diferente da senha temporária."
            )
        return super().clean()

    def save(self, commit=True):
        self.user.deve_trocar_senha = False
        return super().save(commit)


class TrocarSenhaForm(ChangePasswordForm):
    """Trocar a senha em "Minha conta" (formulário do allauth, com os textos do sistema)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _ajustar_campos(
            self,
            {
                "oldpassword": "Senha atual",
                "password1": "Nova senha",
                "password2": "Confirme a nova senha",
            },
        )
        self.fields["password1"].help_text = AJUDA_NOVA_SENHA
