from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.cadastros.models import Produto
from apps.core.dinheiro import ler_decimal_br

QUANTIDADE_MAXIMA = 1_000_000
_MSG_CUSTO = "Custo inválido: use o formato 60,00 (no máximo 4 casas depois da vírgula)."


class _ProdutoPorCodigoForm(forms.Form):
    """Base dos formulários de movimento: o produto vem pelo código digitado."""

    codigo = forms.CharField(label="Código do produto", max_length=40)
    quantidade = forms.IntegerField(
        label="Quantidade",
        min_value=1,
        max_value=QUANTIDADE_MAXIMA,
        error_messages={
            "invalid": "Informe uma quantidade inteira maior que zero.",
            "min_value": "Informe uma quantidade inteira maior que zero.",
            "max_value": "A quantidade é grande demais.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campo = self.fields["codigo"]
        campo.widget.attrs.update({"list": "codigos", "autocomplete": "off", "autofocus": True})
        self.fields["quantidade"].widget.attrs["inputmode"] = "numeric"
        self.produto: Produto | None = None

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().upper()
        self.produto = Produto.objects.filter(codigo=codigo).first()
        if self.produto is None:
            raise ValidationError("Produto não encontrado.")
        return codigo


class _ComCusto(forms.Form):
    custo_unitario = forms.CharField(label="Custo unitário", max_length=20)

    def clean_custo_unitario(self):
        try:
            custo = ler_decimal_br(self.cleaned_data["custo_unitario"])
        except ValueError:
            raise ValidationError(_MSG_CUSTO) from None
        if custo <= 0:
            raise ValidationError("Informe o custo unitário (maior que zero).")
        if custo != custo.quantize(Decimal("0.0001")) or custo >= 10**10:
            raise ValidationError(_MSG_CUSTO)
        return custo


class EstoqueInicialForm(_ProdutoPorCodigoForm, _ComCusto):
    field_order = ["codigo", "quantidade", "custo_unitario"]


class EntradaForm(_ProdutoPorCodigoForm, _ComCusto):
    field_order = ["codigo", "quantidade", "custo_unitario", "observacao"]
    observacao = forms.CharField(label="Observação", max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["observacao"].widget.attrs["placeholder"] = "Ex.: NF 8812"
        self.fields["observacao"].error_messages["required"] = (
            "Informe a observação (ex.: nº da nota)."
        )


class AjusteForm(_ProdutoPorCodigoForm):
    SENTIDOS = [("mais", "Aumentar (+)"), ("menos", "Diminuir (−)")]
    field_order = ["codigo", "sentido", "quantidade", "motivo"]

    sentido = forms.ChoiceField(label="Sentido", choices=SENTIDOS, initial="menos")
    motivo = forms.CharField(label="Motivo", max_length=200)
    confirmar = forms.BooleanField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["motivo"].widget.attrs["placeholder"] = "Ex.: avaria, contagem"
        self.fields["motivo"].error_messages["required"] = "Informe o motivo do ajuste."

    @property
    def delta(self) -> int:
        quantidade = self.cleaned_data["quantidade"]
        return quantidade if self.cleaned_data["sentido"] == "mais" else -quantidade
