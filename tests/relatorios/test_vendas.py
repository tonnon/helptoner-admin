from datetime import date
from decimal import Decimal

from apps.relatorios.consultas import serie, top_produtos
from apps.relatorios.periodos import Agrupamento
from tests.apoio import F


def test_serie_mensal(cenario):
    s = serie(F(date(2026, 9, 1), date(2026, 10, 31)))
    chaves = ("rotulo", "pedidos", "bruto", "descontos", "liquido", "lucro")
    assert [tuple(x[k] for k in chaves) for x in s] == [
        ("set/26", 2, Decimal("350.00"), Decimal("25.00"), Decimal("325.00"), Decimal("125.00")),
        ("out/26", 1, Decimal("150.00"), Decimal("15.00"), Decimal("135.00"), Decimal("75.00")),
    ]  # fmt: skip
    assert s[0]["periodo"] == date(2026, 9, 1)
    assert s[0]["margem"] == Decimal("0.3846") and s[0]["ticket"] == Decimal("162.50")


def test_serie_diaria_com_dias_zerados(cenario):
    s = serie(F(date(2026, 9, 29), date(2026, 10, 1), Agrupamento.DIA))
    assert [(x["rotulo"], x["liquido"]) for x in s] == [
        ("29/09", Decimal("0.00")),
        ("30/09", Decimal("100.00")),
        ("01/10", Decimal("0.00")),
    ]
    assert s[0]["margem"] is None and s[0]["ticket"] is None and s[0]["pedidos"] == 0


def test_serie_semanal_comeca_na_segunda_e_zera_semanas_vazias(cenario):
    # 15/09 é terça (semana de 14/09); 30/09 é quarta (28/09); 02/10 é sexta (28/09).
    s = serie(F(date(2026, 9, 14), date(2026, 10, 4), Agrupamento.SEMANA))
    assert [(x["periodo"], x["rotulo"], x["liquido"]) for x in s] == [
        (date(2026, 9, 14), "14/09", Decimal("225.00")),
        (date(2026, 9, 21), "21/09", Decimal("0.00")),
        (date(2026, 9, 28), "28/09", Decimal("235.00")),
    ]


def test_top_produtos(cenario):
    produtos = top_produtos(F(date(2026, 9, 1), date(2026, 10, 31)))
    assert [(p["codigo"], p["quantidade"], p["faturamento"], p["lucro"]) for p in produtos] == [
        ("CE285A", 3, Decimal("280.00"), Decimal("100.00")),
        ("TN-1060", 4, Decimal("180.00"), Decimal("100.00")),
    ]
    assert produtos[0]["descricao"] == "Toner HP 85A Preto"
    assert produtos[0]["margem"] == Decimal("0.3571")
    assert len(top_produtos(F(date(2026, 9, 1), date(2026, 10, 31)), limite=1)) == 1
