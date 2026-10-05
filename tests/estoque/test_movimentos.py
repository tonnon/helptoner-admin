import re
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from apps.core.erros import EstoqueInsuficiente, RegraDeNegocio
from apps.estoque.services import registrar_ajuste, registrar_entrada, registrar_estoque_inicial
from tests.apoio import com_estoque, criar_produto

pytestmark = pytest.mark.django_db


def test_estoque_inicial(administrador):
    p = criar_produto()
    m = registrar_estoque_inicial(
        produto_id=p.pk, quantidade=10, custo_unitario=Decimal("60.00"), usuario=administrador
    )
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio) == (10, Decimal("60.0000"))
    assert (m.tipo, m.estoque_apos, m.custo_medio_apos, m.usuario) == (
        "inicial",
        10,
        Decimal("60.0000"),
        administrador,
    )


def test_estoque_inicial_uma_vez_so(administrador):
    p = com_estoque(criar_produto(), 10, "60.00")
    with pytest.raises(RegraDeNegocio, match="Este produto já tem movimentos. Use Entrada."):
        registrar_estoque_inicial(
            produto_id=p.pk, quantidade=1, custo_unitario=Decimal("1"), usuario=administrador
        )


def test_entrada_recalcula_o_custo_medio(administrador):
    p = com_estoque(criar_produto(), 10, "60.00")
    m = registrar_entrada(
        produto_id=p.pk,
        quantidade=10,
        custo_unitario=Decimal("80.00"),
        observacao="NF 8812",
        usuario=administrador,
    )
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio, m.motivo) == (20, Decimal("70.0000"), "NF 8812")


@pytest.mark.parametrize(
    "campos,mensagem",
    [
        ({"observacao": ""}, "Informe a observação (ex.: nº da nota)."),
        ({"custo_unitario": Decimal("0")}, "Informe o custo unitário (maior que zero)."),
        ({"quantidade": 0}, "Informe uma quantidade inteira maior que zero."),
    ],
)
def test_entrada_exige_dados(administrador, campos, mensagem):
    p = com_estoque(criar_produto(), 1, "60.00")
    dados = {
        "produto_id": p.pk,
        "quantidade": 1,
        "custo_unitario": Decimal("1"),
        "observacao": "NF 1",
        "usuario": administrador,
    } | campos
    with pytest.raises(RegraDeNegocio, match=re.escape(mensagem)):
        registrar_entrada(**dados)


def test_ajuste_negativo_nao_deixa_o_estoque_negativo(administrador):
    p = com_estoque(criar_produto(), 3, "60.00")
    with pytest.raises(
        EstoqueInsuficiente, match="O estoque atual é 3; o ajuste deixaria o estoque negativo."
    ):
        registrar_ajuste(produto_id=p.pk, delta=-4, motivo="avaria", usuario=administrador)
    registrar_ajuste(produto_id=p.pk, delta=-3, motivo="avaria", usuario=administrador)
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio) == (0, Decimal("60.0000"))  # zerado mantém o último custo


def test_ajuste_positivo_entra_pelo_custo_medio(administrador):
    p = com_estoque(criar_produto(), 10, "60.00")
    m = registrar_ajuste(produto_id=p.pk, delta=2, motivo="contagem", usuario=administrador)
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio, m.tipo, m.custo_unitario) == (
        12,
        Decimal("60.0000"),
        "ajuste_mais",
        Decimal("60.0000"),
    )


def test_ajuste_positivo_recusado_sem_custo(administrador):
    p = criar_produto()
    with pytest.raises(
        RegraDeNegocio,
        match=(
            "Este produto ainda não tem custo. "
            "Lance o estoque inicial ou uma entrada antes do ajuste."
        ),
    ):
        registrar_ajuste(produto_id=p.pk, delta=1, motivo="contagem", usuario=administrador)


def test_ajuste_exige_motivo_e_quantidade(administrador):
    p = com_estoque(criar_produto(), 1, "60.00")
    with pytest.raises(RegraDeNegocio, match="Informe o motivo do ajuste."):
        registrar_ajuste(produto_id=p.pk, delta=1, motivo=" ", usuario=administrador)
    with pytest.raises(RegraDeNegocio, match="Informe uma quantidade inteira maior que zero."):
        registrar_ajuste(produto_id=p.pk, delta=0, motivo="x", usuario=administrador)


def test_vendedor_nao_movimenta(vendedor):
    p = criar_produto()
    with pytest.raises(PermissionDenied):
        registrar_estoque_inicial(
            produto_id=p.pk, quantidade=1, custo_unitario=Decimal("1"), usuario=vendedor
        )


def test_movimento_nao_gera_historico_do_produto(administrador):
    p = com_estoque(criar_produto(), 10, "60.00")
    registrar_ajuste(produto_id=p.pk, delta=-1, motivo="avaria", usuario=administrador)
    assert p.history.count() == 1
