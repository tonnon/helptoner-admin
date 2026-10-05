import random
from decimal import Decimal

import pytest

from apps.pedidos.calculos import Linha, Totais, calcular_totais, margem, ratear_desconto


def L(*pares):
    return [Linha(q, Decimal(p)) for q, p in pares]


def test_totais_com_percentual():
    assert calcular_totais(L((2, "189.90"), (3, "89.90")), "percentual", Decimal("10")) == Totais(
        Decimal("649.50"), Decimal("64.95"), Decimal("584.55"), None
    )


def test_percentual_arredonda_meio_para_cima():
    assert calcular_totais(
        L((1, "649.50")), "percentual", Decimal("33.333")
    ).desconto_valor == Decimal("216.50")
    assert calcular_totais(L((1, "0.05")), "percentual", Decimal("50")).desconto_valor == Decimal(
        "0.03"
    )


def test_desconto_em_reais_ate_o_subtotal():
    assert calcular_totais(L((1, "649.50")), "reais", Decimal("649.50")).total == Decimal("0.00")
    t = calcular_totais(L((1, "649.50")), "reais", Decimal("649.51"))
    assert (t.desconto_valor, t.total, t.erro_desconto) == (
        Decimal("0"),
        Decimal("649.50"),
        "O desconto não pode passar do subtotal.",
    )


def test_erros_de_desconto():
    assert (
        calcular_totais(L((1, "10")), "percentual", Decimal("100.01")).erro_desconto
        == "O desconto não pode passar de 100%."
    )
    assert (
        calcular_totais(L((1, "10")), "reais", Decimal("-1")).erro_desconto
        == "O desconto não pode ser negativo."
    )


def test_pedido_vazio_nao_mostra_erro_de_desconto():
    assert calcular_totais([], "reais", Decimal("10")) == Totais(
        Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), None
    )


def test_rateio_proporcional():
    assert ratear_desconto([Decimal("200.00"), Decimal("50.00")], Decimal("25.00")) == [
        Decimal("20.00"),
        Decimal("5.00"),
    ]
    assert sum(
        ratear_desconto([Decimal("33.33"), Decimal("33.33"), Decimal("33.34")], Decimal("10.00"))
    ) == Decimal("10.00")
    assert ratear_desconto([Decimal("0.00"), Decimal("0.00")], Decimal("0.00")) == [
        Decimal("0.00"),
        Decimal("0.00"),
    ]


def test_rateio_nunca_negativo_nem_maior_que_o_item():
    rnd = random.Random(42)
    for _ in range(500):
        itens = [Decimal(rnd.randint(1, 50000)) / 100 for _ in range(rnd.randint(1, 8))]
        desconto = Decimal(rnd.randint(0, int(sum(itens) * 100))) / 100
        partes = ratear_desconto(itens, desconto)
        assert sum(partes) == desconto and all(
            Decimal(0) <= p <= t for p, t in zip(partes, itens, strict=True)
        )
    assert ratear_desconto([Decimal("0.01")] * 4, Decimal("0.02")) == [
        Decimal("0.01"),
        Decimal("0.00"),
        Decimal("0.01"),
        Decimal("0.00"),
    ]


def test_rateio_rejeita_desconto_invalido():
    with pytest.raises(ValueError):
        ratear_desconto([Decimal("10.00")], Decimal("-0.01"))
    with pytest.raises(ValueError):
        ratear_desconto([Decimal("10.00")], Decimal("10.01"))


def test_margem():
    assert margem(Decimal("125.00"), Decimal("325.00")) == Decimal("0.3846")
    assert margem(Decimal("-10"), Decimal("100")) == Decimal("-0.1000")
    assert margem(Decimal("0"), Decimal("0")) is None


@pytest.mark.parametrize("tipo", ["percent", "", None])
def test_tipo_de_desconto_invalido_e_recusado(tipo):
    with pytest.raises(ValueError):
        calcular_totais(L((1, "10")), tipo, Decimal("1"))
    with pytest.raises(ValueError):
        calcular_totais([], tipo, Decimal("1"))


def test_percentual_negativo_da_erro_de_negativo():
    t = calcular_totais(L((1, "10")), "percentual", Decimal("-5"))
    assert (t.erro_desconto, t.desconto_valor) == (
        "O desconto não pode ser negativo.",
        Decimal("0.00"),
    )


def test_subtotal_zero_com_itens_nao_da_erro():
    t = calcular_totais(L((1, "0.00")), "reais", Decimal("-1"))
    assert t == Totais(Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), None)


def test_total_da_linha_arredonda_meio_para_cima():
    assert Linha(3, Decimal("0.335")).total == Decimal("1.01")


def test_margem_receita_negativa_e_meio_para_cima():
    assert margem(Decimal("5"), Decimal("-10")) is None
    assert margem(Decimal("1"), Decimal("32")) == Decimal("0.0313")
