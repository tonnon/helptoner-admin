import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.core.dinheiro import ler_decimal_br

from .models import Pedido
from .services import MSG_QUANTIDADE, MSG_QUANTIDADE_MAXIMA, QUANTIDADE_MAXIMA

MSG_ESCOLHA_PRODUTO = "Escolha um produto na lista de sugestões."
MSG_ESCOLHA_CLIENTE = "Escolha um cliente na lista de sugestões."
MSG_NUMERO = "Informe um número. Ex.: 10 ou 10,5"
MSG_TIPO_DESCONTO = "Tipo de desconto inválido."

_SO_DIGITOS = re.compile(r"\d+", re.ASCII)
_DIGITOS_DO_MAXIMO = len(str(QUANTIDADE_MAXIMA))


def _id(mensagem: str) -> forms.IntegerField:
    """Id escolhido numa lista de sugestões: qualquer valor que não seja um id vira `mensagem`."""
    return forms.IntegerField(
        min_value=1,
        error_messages={"required": mensagem, "invalid": mensagem, "min_value": mensagem},
    )


class QuantidadeForm(forms.Form):
    """Quantidade digitada: só algarismos, de 1 a 9.999 (as mensagens são as do serviço)."""

    quantidade = forms.CharField(required=False)

    def clean_quantidade(self) -> int:
        texto = self.cleaned_data["quantidade"]
        if not _SO_DIGITOS.fullmatch(texto):
            raise ValidationError(MSG_QUANTIDADE)
        # Sem os zeros à esquerda, antes do int(): texto enorme não chega a virar número.
        digitos = texto.lstrip("0")
        if not digitos:
            raise ValidationError(MSG_QUANTIDADE)
        if len(digitos) > _DIGITOS_DO_MAXIMO or int(digitos) > QUANTIDADE_MAXIMA:
            raise ValidationError(MSG_QUANTIDADE_MAXIMA)
        return int(digitos)


class ItemForm(QuantidadeForm):
    field_order = ["produto_id", "quantidade"]

    produto_id = _id(MSG_ESCOLHA_PRODUTO)


class ClienteForm(forms.Form):
    cliente_id = _id(MSG_ESCOLHA_CLIENTE)


class DescontoForm(forms.Form):
    """Desconto do rascunho. Campo vazio vale zero (sem desconto)."""

    tipo = forms.ChoiceField(
        choices=Pedido.TipoDesconto.choices,
        error_messages={"required": MSG_TIPO_DESCONTO, "invalid_choice": MSG_TIPO_DESCONTO},
    )
    valor = forms.CharField(
        required=False, max_length=20, error_messages={"max_length": MSG_NUMERO}
    )

    def clean_valor(self) -> Decimal:
        texto = self.cleaned_data["valor"]
        if not texto:
            return Decimal("0")
        try:
            return ler_decimal_br(texto)
        except ValueError:
            raise ValidationError(MSG_NUMERO) from None
