from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.core.datas import hoje
from apps.relatorios.consultas import (
    ABAS,
    cancelamentos,
    estoque,
    funcionarios,
    marcas,
    montar_aba,
    produtos,
    ranking_clientes,
)
from tests.apoio import F

TUDO = F(date(2026, 9, 1), date(2026, 10, 31))
TIPOS = {
    "dinheiro": Decimal,
    "inteiro": int,
    "percentual": Decimal,
    "data": date,
    "texto": str,
}


def test_produtos_e_marcas(cenario):
    assert [
        (p["codigo"], p["quantidade"], p["faturamento"], p["lucro"], p["margem"], p["participacao"])
        for p in produtos(TUDO)
    ] == [
        ("CE285A", 3, Decimal("280.00"), Decimal("100.00"), Decimal("0.3571"), Decimal("0.6087")),
        ("TN-1060", 4, Decimal("180.00"), Decimal("100.00"), Decimal("0.5556"), Decimal("0.3913")),
    ]
    assert [(m["marca"], m["faturamento"]) for m in marcas(TUDO)] == [
        ("HP", Decimal("280.00")),
        ("Brother", Decimal("180.00")),
    ]


def test_produtos_sem_vendas(cenario):
    assert produtos(F(date(2026, 8, 1), date(2026, 8, 31))) == []
    assert marcas(F(date(2026, 8, 1), date(2026, 8, 31))) == []


def test_funcionarios(cenario):
    assert [
        (x["nome"], x["pedidos"], x["valor"], x["lucro"], x["desconto_medio"])
        for x in funcionarios(TUDO)
    ] == [
        ("Carla Souza", 2, Decimal("360.00"), Decimal("160.00"), Decimal("0.1000")),
        ("Lucas Tonnon", 1, Decimal("100.00"), Decimal("40.00"), Decimal("0.0000")),
    ]


def test_ranking_de_clientes(cenario):
    assert [
        (x["nome"], x["valor"], x["pedidos"], x["lucro"], x["ultimo_pedido"])
        for x in ranking_clientes(TUDO)
    ] == [
        ("Papelaria Central Ltda", Decimal("360.00"), 2, Decimal("160.00"), date(2026, 10, 2)),
        ("Clínica Bem Viver", Decimal("100.00"), 1, Decimal("40.00"), date(2026, 9, 30)),
    ]


def test_ultimo_pedido_vale_em_qualquer_periodo(cenario):
    setembro = ranking_clientes(F(date(2026, 9, 1), date(2026, 9, 30)))
    assert [(x["nome"], x["ultimo_pedido"]) for x in setembro] == [
        ("Papelaria Central Ltda", date(2026, 10, 2)),
        ("Clínica Bem Viver", date(2026, 9, 30)),
    ]


def test_cancelamentos_pela_data_do_cancelamento(cenario):
    assert [
        (x["numero"], x["valor"], x["motivo"], x["cancelado_por"])
        for x in cancelamentos(F(date(2026, 10, 1), date(2026, 10, 31)))
    ] == [(4, Decimal("50.00"), "Cliente desistiu", "Lucas Tonnon")]
    assert cancelamentos(F(date(2026, 10, 1), date(2026, 10, 2))) == []


def test_cancelamentos_filtram_por_quem_emitiu(cenario):
    periodo = (date(2026, 10, 1), date(2026, 10, 31))
    linha = cancelamentos(F(*periodo, funcionario_id=cenario.lucas.pk))[0]
    assert linha["emitido_por"] == "Lucas Tonnon" and linha["cliente"] == "Clínica Bem Viver"
    assert cancelamentos(F(*periodo, funcionario_id=cenario.carla.pk)) == []


def test_estoque(cenario):
    dia = hoje()
    e = estoque(F(dia - timedelta(days=1), dia + timedelta(days=1)))
    assert [
        (p["codigo"], p["estoque"], p["custo_medio"], p["valor_em_estoque"]) for p in e["produtos"]
    ] == [
        ("CE285A", 97, Decimal("60.0000"), Decimal("5820.00")),
        ("CF217A", 0, Decimal("0.0000"), Decimal("0.00")),
        ("TN-1060", 96, Decimal("20.0000"), Decimal("1920.00")),
    ]
    assert e["zerados"] == ["CF217A"] and e["valor_total"] == Decimal("7740.00")
    assert e["movimentos"] == {
        "entradas": 200,
        "saidas": 8,
        "devolucoes": 1,
        "ajustes_mais": 0,
        "ajustes_menos": 0,
    }


def test_estoque_movimentos_fora_do_periodo_e_por_funcionario(cenario):
    assert estoque(F(date(2026, 8, 1), date(2026, 8, 31)))["movimentos"]["saidas"] == 0
    dia = hoje()
    f = F(dia, dia, funcionario_id=cenario.carla.pk)
    assert estoque(f)["movimentos"] == {
        "entradas": 0,
        "saidas": 6,
        "devolucoes": 0,
        "ajustes_mais": 0,
        "ajustes_menos": 0,
    }


def test_estoque_ignora_produto_inativo(cenario):
    cenario.cf217a.ativo = False
    cenario.cf217a.save()
    e = estoque(TUDO)
    assert [p["codigo"] for p in e["produtos"]] == ["CE285A", "TN-1060"] and e["zerados"] == []


@pytest.mark.parametrize("aba", list(ABAS))
def test_montar_aba(cenario, aba):
    rel = montar_aba(aba, TUDO, date(2026, 12, 1))
    assert rel.titulo == ABAS[aba] and rel.tabelas
    assert all(len(linha) == len(t.colunas) for t in rel.tabelas for linha in t.linhas)
    for tabela in rel.tabelas:
        for linha in tabela.linhas:
            for coluna, valor in zip(tabela.colunas, linha, strict=True):
                if valor is None:
                    assert coluna.tipo == "percentual"
                else:
                    assert type(valor) is TIPOS[coluna.tipo], (tabela.titulo, coluna.rotulo)


def test_resumo_tem_comparacao_e_graficos(cenario):
    rel = montar_aba("resumo", TUDO, date(2026, 12, 1))
    assert rel.comparacao is not None and rel.graficos is not None
    assert montar_aba("estoque", TUDO, date(2026, 12, 1)).graficos is None


def test_clientes_sem_comprar_usa_os_dias_pedidos(cenario):
    rel = montar_aba("clientes", TUDO, date(2026, 11, 10), dias_sem_comprar=40)
    assert [linha[0] for linha in rel.tabelas[1].linhas] == ["Clínica Bem Viver"]
