from django import forms
from django.core.exceptions import ValidationError

from .documentos import normalizar_documento, validar_documento
from .models import Cliente


def mensagem_documento_repetido(outro) -> str:
    if outro is None:
        return "Já existe um cliente com este CPF/CNPJ."
    return f"Já existe um cliente com este CPF/CNPJ: {outro.nome}."


class ClienteForm(forms.ModelForm):
    # Sem o limite de 14: a pessoa digita com a máscara (18 caracteres no CNPJ).
    documento = forms.CharField(label="CPF/CNPJ", max_length=30)
    cep = forms.CharField(label="CEP", max_length=20, required=False)

    class Meta:
        model = Cliente
        fields = [
            "tipo",
            "nome",
            "documento",
            "telefone",
            "email",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
            "observacoes",
        ]
        widgets = {"tipo": forms.RadioSelect, "observacoes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sem a opção em branco do seletor segmentado.
        self.fields["tipo"].choices = [c for c in self.fields["tipo"].choices if c[0]]
        for nome, mascara in (("documento", "cnpj"), ("cep", "cep"), ("telefone", "telefone")):
            self.fields[nome].widget.attrs["data-mascara"] = mascara
        self.fields["nome"].widget.attrs["autocomplete"] = "off"

    def clean_documento(self):
        return normalizar_documento(self.cleaned_data["documento"])

    def clean_cep(self):
        return normalizar_documento(self.cleaned_data.get("cep", ""))

    def clean(self):
        dados = super().clean()
        tipo, documento = dados.get("tipo"), dados.get("documento")
        if tipo and documento:
            try:
                validar_documento(tipo, documento)
            except ValidationError:
                return dados  # o erro de dígitos vem do modelo (Cliente.clean)
            outro = Cliente.objects.filter(documento=documento).exclude(pk=self.instance.pk).first()
            if outro:
                self.add_error("documento", mensagem_documento_repetido(outro))

        return dados

    def validate_unique(self):
        """A unicidade do documento já foi conferida em clean(), com a mensagem do sistema."""
