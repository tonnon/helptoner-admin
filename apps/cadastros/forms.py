from django import forms
from django.core.exceptions import ValidationError

from apps.core.dinheiro import CENTAVO, ler_decimal_br

from .documentos import normalizar_documento, validar_documento
from .models import Cliente, Produto


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


class ProdutoForm(forms.ModelForm):
    # Texto livre: o preço é lido à brasileira ("1.234,56").
    preco = forms.CharField(label="Preço (R$)", max_length=20)

    class Meta:
        model = Produto
        fields = ["codigo", "descricao", "marca", "preco"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["codigo"].widget.attrs.update({"autocomplete": "off", "autofocus": True})
        self.fields["preco"].widget.attrs["inputmode"] = "decimal"
        if self.instance.pk:
            self.initial["preco"] = f"{self.instance.preco:.2f}".replace(".", ",")

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip().upper()

    def clean_preco(self):
        try:
            preco = ler_decimal_br(self.cleaned_data["preco"])
        except ValueError:
            raise ValidationError("Preço inválido: use o formato 189,90.") from None
        if preco < 0:
            raise ValidationError("O preço não pode ser negativo.")
        if preco != preco.quantize(CENTAVO) or preco >= 10**10:
            raise ValidationError("Preço inválido: use no máximo 2 casas depois da vírgula.")
        return preco
