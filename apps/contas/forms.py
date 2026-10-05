from allauth.account.forms import ChangePasswordForm
from django import forms
from django.contrib.auth.forms import SetPasswordForm

from .models import ADMINISTRADOR, VENDEDOR

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
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.deve_trocar_senha = False
        if commit:
            # Só os campos trocados: um save() inteiro desfaria uma desativação feita ao mesmo
            # tempo por um administrador (§4.2: quem é desativado perde o acesso na hora).
            self.user.save(update_fields=["password", "deve_trocar_senha"])
        return self.user


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


class FuncionarioForm(forms.Form):
    """Editar um funcionário: nome e perfil (o e-mail é o login e não muda por aqui)."""

    nome = forms.CharField(
        label="Nome", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    perfil = forms.ChoiceField(
        label="Perfil",
        choices=[(VENDEDOR, VENDEDOR), (ADMINISTRADOR, ADMINISTRADOR)],
        initial=VENDEDOR,
        help_text=(
            "O Administrador também cadastra produtos, cuida do estoque, cancela pedidos, vê "
            "custos e relatórios e gerencia funcionários."
        ),
    )

    def __init__(self, *args, travar_perfil=False, **kwargs):
        super().__init__(*args, **kwargs)
        if travar_perfil:  # o Administrador editando a si mesmo (P13)
            self.fields["perfil"].disabled = True
            self.fields["perfil"].help_text = "Você não pode mudar o seu próprio perfil."


class NovoFuncionarioForm(FuncionarioForm):
    """Cadastrar um funcionário. A senha temporária é gerada pelo sistema."""

    email = forms.EmailField(
        label="E-mail", max_length=254, widget=forms.EmailInput(attrs={"autocomplete": "off"})
    )

    field_order = ["nome", "email", "perfil"]
