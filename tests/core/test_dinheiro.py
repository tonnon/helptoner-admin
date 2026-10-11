from decimal import Decimal

import pytest

from apps.core.dinheiro import arredondar, arredondar_custo, ler_decimal_br


@pytest.mark.parametrize(
    "valor,esperado",
    [("0.005", "0.01"), ("0.015", "0.02"), ("2.675", "2.68"), ("-0.005", "-0.01")],
)
def test_arredondar_meio_para_cima(valor, esperado):
    assert arredondar(Decimal(valor)) == Decimal(esperado)


def test_arredondar_custo_com_4_casas():
    assert arredondar_custo(Decimal("68.888888")) == Decimal("68.8889")


@pytest.mark.parametrize(
    "texto,esperado",
    [("1.234,56", "1234.56"), ("10,5", "10.5"), (" 7 ", "7"), ("1.000", "1000"), ("-3", "-3")],
)
def test_ler_decimal_br(texto, esperado):
    assert ler_decimal_br(texto) == Decimal(esperado)


@pytest.mark.parametrize("texto", ["", "abc", "1,2,3", "10%", "1e3", "NaN", "Infinity", "1.23,4.5"])
def test_ler_decimal_br_recusa_lixo(texto):
    with pytest.raises(ValueError):
        ler_decimal_br(texto)
