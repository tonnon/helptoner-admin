from datetime import date
from decimal import Decimal

from apps.relatorios.consultas import Indicadores, clientes_sem_comprar, comparar, indicadores
from tests.apoio import F

SET = F(date(2026, 9, 1), date(2026, 9, 30))


def test_indicadores_de_setembro(cenario):
    assert indicadores(SET) == Indicadores(
        Decimal("325.00"), Decimal("125.00"), Decimal("0.3846"), 2, Decimal("162.50")
    )


def test_filtro_de_funcionario(cenario):
    filtros = F(date(2026, 9, 1), date(2026, 9, 30), funcionario_id=cenario.carla.pk)
    assert indicadores(filtros) == Indicadores(
        Decimal("225.00"), Decimal("85.00"), Decimal("0.3778"), 1, Decimal("225.00")
    )


def test_borda_do_fuso_cancelado_e_rascunho(cenario):
    assert indicadores(F(date(2026, 10, 1), date(2026, 10, 3))) == Indicadores(
        Decimal("135.00"), Decimal("75.00"), Decimal("0.5556"), 1, Decimal("135.00")
    )


def test_periodo_sem_vendas(cenario):
    assert indicadores(F(date(2026, 8, 1), date(2026, 8, 31))) == Indicadores(
        Decimal("0.00"), Decimal("0.00"), None, 0, None
    )


def test_comparacao_com_o_periodo_anterior(cenario):
    c = comparar(F(date(2026, 10, 1), date(2026, 10, 3)))  # anterior: 28 a 30/09, só o nº 2
    assert c.anterior.faturamento == Decimal("100.00") and c.descricao == "vs 3 dias anteriores"
    variacoes = (
        c.variacao("faturamento"),
        c.variacao("lucro"),
        c.variacao("margem"),
        c.variacao("pedidos"),
    )
    assert variacoes == (Decimal("0.3500"), Decimal("0.8750"), Decimal("0.1556"), 0)
    assert comparar(SET).variacao("faturamento") is None  # agosto sem vendas


def test_clientes_sem_comprar(cenario):  # C1: 60 dias (fica de fora); C2: 62 dias
    r = clientes_sem_comprar(60, date(2026, 12, 1))
    assert [
        (x["nome"], x["ultimo_pedido"], x["dias"], x["produtos"], x["ultimo_pedido_id"]) for x in r
    ] == [("Clínica Bem Viver", date(2026, 9, 30), 62, ["CE285A"], cenario.pedido2.pk)]


def test_clientes_sem_comprar_ignora_cancelado_e_filtra_funcionario(cenario):
    # O nº 4 (cancelado, 02/10) não conta como compra; com 59 dias, C1 (60) também aparece.
    r = clientes_sem_comprar(59, date(2026, 12, 1))
    assert [(x["nome"], x["dias"], x["produtos"]) for x in r] == [
        ("Clínica Bem Viver", 62, ["CE285A"]),
        ("Papelaria Central Ltda", 60, ["TN-1060"]),
    ]
    so_carla = clientes_sem_comprar(59, date(2026, 12, 1), cenario.carla.pk)
    assert [x["nome"] for x in so_carla] == ["Papelaria Central Ltda"]
