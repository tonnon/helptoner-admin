"""Cálculos do pedido (funções puras, sem banco): totais, desconto, rateio e margem."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.core.dinheiro import arredondar

DESCONTO_REAIS = "reais"
DESCONTO_PERCENTUAL = "percentual"

_ZERO = Decimal("0.00")
_CEM = Decimal("100")
_CASAS_DA_MARGEM = Decimal("0.0001")


@dataclass(frozen=True)
class Linha:
    quantidade: int
    preco_unitario: Decimal

    @property
    def total(self) -> Decimal:
        return arredondar(self.preco_unitario * self.quantidade)


@dataclass(frozen=True)
class Totais:
    subtotal: Decimal
    desconto_valor: Decimal
    total: Decimal
    erro_desconto: str | None


def _erro_do_desconto(subtotal: Decimal, desconto_tipo: str, informado: Decimal) -> str | None:
    if informado < 0:
        return "O desconto não pode ser negativo."
    if desconto_tipo == DESCONTO_PERCENTUAL:
        if informado > _CEM:
            return "O desconto não pode passar de 100%."
    elif informado > subtotal:
        return "O desconto não pode passar do subtotal."
    return None


def calcular_totais(
    linhas: Sequence[Linha], desconto_tipo: str, desconto_informado: Decimal
) -> Totais:
    if desconto_tipo not in (DESCONTO_REAIS, DESCONTO_PERCENTUAL):
        raise ValueError(f"Tipo de desconto inválido: {desconto_tipo!r}")
    subtotal = sum((linha.total for linha in linhas), _ZERO)
    if subtotal == 0:
        return Totais(subtotal, _ZERO, subtotal, None)
    erro = _erro_do_desconto(subtotal, desconto_tipo, desconto_informado)
    if erro:
        return Totais(subtotal, _ZERO, subtotal, erro)
    if desconto_tipo == DESCONTO_PERCENTUAL:
        desconto = arredondar(subtotal * desconto_informado / _CEM)
    else:
        desconto = arredondar(desconto_informado)
    return Totais(subtotal, desconto, subtotal - desconto, None)


def ratear_desconto(totais_itens: Sequence[Decimal], desconto: Decimal) -> list[Decimal]:
    """Divide o desconto entre os itens, proporcional ao total de cada um.

    Usa arredondamento acumulado: a soma das partes é sempre o desconto, e nenhuma
    parte fica negativa nem passa do total do item.
    """
    subtotal = sum(totais_itens, Decimal("0"))
    if desconto < 0 or desconto > subtotal:
        raise ValueError("Desconto fora do intervalo de 0 até a soma dos itens.")
    acumulado, distribuido, partes = Decimal("0"), _ZERO, []
    for total in totais_itens:
        acumulado += total
        alvo = arredondar(desconto * acumulado / subtotal) if subtotal else _ZERO
        partes.append(alvo - distribuido)
        distribuido = alvo
    return partes


def margem(lucro: Decimal, receita: Decimal) -> Decimal | None:
    """Lucro dividido pela receita, com 4 casas; None quando a receita é 0 ou menor."""
    if receita <= 0:
        return None
    return (lucro / receita).quantize(_CASAS_DA_MARGEM, rounding=ROUND_HALF_UP)
