from datetime import date
from urllib.parse import parse_qsl

import pytest

from apps.relatorios.periodos import (
    Agrupamento,
    Atalho,
    Filtros,
    descricao_comparacao,
    deslocar_meses,
    ler_dias_sem_comprar,
    ler_filtros,
    periodo_anterior,
    periodo_do_atalho,
)

HOJE = date(2026, 10, 3)


def test_atalhos():
    assert periodo_do_atalho(Atalho.TRES_MESES, HOJE) == (date(2026, 8, 1), HOJE)
    assert periodo_do_atalho(Atalho.DOZE_MESES, HOJE) == (date(2025, 11, 1), HOJE)
    assert periodo_do_atalho(Atalho.ANO, HOJE) == (date(2026, 1, 1), HOJE)


@pytest.mark.parametrize(
    "atalho,inicio,fim,anterior",
    [
        (Atalho.TRES_MESES, date(2026, 8, 1), HOJE, (date(2026, 5, 1), date(2026, 7, 3))),
        (Atalho.DOZE_MESES, date(2025, 11, 1), HOJE, (date(2024, 11, 1), date(2025, 10, 3))),
        (Atalho.ANO, date(2026, 1, 1), HOJE, (date(2025, 1, 1), date(2025, 10, 3))),
        (Atalho.DATAS, date(2026, 10, 1), HOJE, (date(2026, 9, 28), date(2026, 9, 30))),
    ],
)
def test_periodo_anterior(atalho, inicio, fim, anterior):
    f = Filtros(inicio, fim, Agrupamento.MES, None, atalho)
    p = periodo_anterior(f)
    assert (p.inicio, p.fim) == anterior


def test_deslocar_meses_no_fim_do_mes():
    assert deslocar_meses(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert deslocar_meses(date(2024, 2, 29), -12) == date(2023, 2, 28)
    assert deslocar_meses(date(2026, 1, 15), -2) == date(2025, 11, 15)
    assert deslocar_meses(date(2026, 11, 30), 3) == date(2027, 2, 28)


def test_descricao_comparacao():
    def f(atalho, inicio, fim):
        return Filtros(inicio, fim, Agrupamento.MES, None, atalho)

    assert (
        descricao_comparacao(f(Atalho.TRES_MESES, date(2026, 8, 1), HOJE))
        == "vs 3 meses anteriores"
    )
    assert (
        descricao_comparacao(f(Atalho.DOZE_MESES, date(2025, 11, 1), HOJE))
        == "vs 12 meses anteriores"
    )
    assert descricao_comparacao(f(Atalho.ANO, date(2026, 1, 1), HOJE)) == "vs mesmo período de 2025"
    assert descricao_comparacao(f(Atalho.DATAS, date(2026, 10, 1), HOJE)) == "vs 3 dias anteriores"
    assert descricao_comparacao(f(Atalho.DATAS, HOJE, HOJE)) == "vs 1 dia anterior"


def test_padrao_e_erros():
    f, erros = ler_filtros({}, HOJE)
    assert (f.atalho, f.inicio, f.fim, f.agrupamento, f.funcionario_id, erros) == (
        Atalho.DOZE_MESES,
        date(2025, 11, 1),
        HOJE,
        Agrupamento.MES,
        None,
        [],
    )
    _, erros = ler_filtros({"atalho": "datas", "inicio": "2026-10-05", "fim": "2026-10-01"}, HOJE)
    assert erros == ["A data inicial precisa ser antes da final."]
    _, erros = ler_filtros(
        {"atalho": "datas", "inicio": "2024-01-01", "fim": "2026-10-03", "agrupamento": "dia"}, HOJE
    )
    assert erros == ["Para agrupar por dia, escolha um período de até 366 dias."]
    _, erros = ler_filtros({"funcionario": "abc"}, HOJE)
    assert erros == ["Funcionário inválido."]


def test_erros_voltam_ao_padrao():
    f, erros = ler_filtros(
        {"atalho": "datas", "inicio": "2026-10-05", "fim": "2026-10-01", "agrupamento": "dia"}, HOJE
    )
    assert erros == ["A data inicial precisa ser antes da final."]
    assert (f.atalho, f.inicio, f.fim) == (Atalho.DOZE_MESES, date(2025, 11, 1), HOJE)
    f, erros = ler_filtros({"atalho": "x", "agrupamento": "y", "funcionario": "0"}, HOJE)
    assert erros == ["Período inválido.", "Agrupamento inválido.", "Funcionário inválido."]
    assert (f.atalho, f.agrupamento, f.funcionario_id) == (Atalho.DOZE_MESES, Agrupamento.MES, None)


@pytest.mark.parametrize(
    "valor", ["lixo", "2026-13-01", "9999-12-31", "1999-12-31", "2101-01-01", "", "20261003"]
)
def test_datas_invalidas_ou_fora_da_faixa(valor):
    f, erros = ler_filtros({"atalho": "datas", "inicio": valor, "fim": "2026-10-01"}, HOJE)
    assert erros == ["Data inicial inválida."]
    assert f.atalho == Atalho.DOZE_MESES
    f, erros = ler_filtros({"atalho": "datas", "inicio": "2026-10-01", "fim": valor}, HOJE)
    assert erros == ["Data final inválida."]


def test_dia_aceita_366_dias_e_recusa_367():
    d = {"atalho": "datas", "agrupamento": "dia"}
    f, erros = ler_filtros({**d, "inicio": "2025-10-03", "fim": "2026-10-03"}, HOJE)
    assert erros == [] and f.agrupamento == Agrupamento.DIA
    f, erros = ler_filtros({**d, "inicio": "2025-10-02", "fim": "2026-10-03"}, HOJE)
    assert len(erros) == 1 and f.agrupamento == Agrupamento.MES


@pytest.mark.parametrize(
    "dados",
    [
        {},
        {"atalho": "3m", "agrupamento": "semana", "funcionario": "7"},
        {"atalho": "ano", "agrupamento": "dia"},
        {
            "atalho": "datas",
            "inicio": "2026-09-01",
            "fim": "2026-10-03",
            "agrupamento": "dia",
            "funcionario": "12",
        },
    ],
)
def test_querystring_ida_e_volta(dados):
    f, erros = ler_filtros(dados, HOJE)
    assert erros == []
    volta, erros = ler_filtros(dict(parse_qsl(f.como_querystring())), HOJE)
    assert erros == []
    assert volta == f


@pytest.mark.parametrize(
    ("dados", "esperado"),
    [
        ({}, (60, [])),
        ({"dias": " 40 "}, (40, [])),
        ({"dias": "3650"}, (3650, [])),
        ({"dias": "0"}, (60, ["Número de dias inválido."])),
        ({"dias": "3651"}, (60, ["Número de dias inválido."])),
        ({"dias": "-5"}, (60, ["Número de dias inválido."])),
        ({"dias": "٤٠"}, (60, ["Número de dias inválido."])),  # dígitos não ASCII
        ({"dias": "9" * 5000}, (60, ["Número de dias inválido."])),
    ],
)
def test_dias_sem_comprar(dados, esperado):
    assert ler_dias_sem_comprar(dados) == esperado
