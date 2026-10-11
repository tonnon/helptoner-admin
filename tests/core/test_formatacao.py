from datetime import UTC, date, datetime
from decimal import Decimal

from django.template import Context, Template

from apps.core.datas import hoje, intervalo_de_datas, mes_de
from apps.core.formatacao import (
    brl,
    data_br,
    data_hora_br,
    inteiro_br,
    numero_pedido,
    percentual,
)


def test_formatos():
    assert brl(Decimal("1234.5")) == "R$ 1.234,50"
    assert brl(Decimal("1234567.891")) == "R$ 1.234.567,89"
    assert brl(Decimal("0")) == "R$ 0,00" and brl(Decimal("-254.85")) == "-R$ 254,85"
    assert brl(None) == "—"
    assert numero_pedido(1042) == "nº 1.042" and numero_pedido(7) == "nº 7"
    assert numero_pedido(None) == "—"
    assert inteiro_br(1234567) == "1.234.567"
    assert percentual(Decimal("0.3846")) == "38,5%" and percentual(Decimal("-0.05")) == "-5,0%"
    assert percentual(None) == "—"
    assert data_hora_br(datetime(2026, 11, 1, 1, 30, tzinfo=UTC)) == "31/10/2026 22:30"
    assert data_br(datetime(2026, 11, 1, 1, 30, tzinfo=UTC)) == "31/10/2026"
    assert data_br(date(2026, 10, 2)) == "02/10/2026"


def test_datas_de_brasilia():
    assert hoje(datetime(2026, 11, 1, 2, 0, tzinfo=UTC)) == date(2026, 10, 31)
    assert intervalo_de_datas(date(2026, 10, 1), date(2026, 10, 31)) == (
        datetime(2026, 10, 1, 3, 0, tzinfo=UTC),
        datetime(2026, 11, 1, 3, 0, tzinfo=UTC),
    )
    assert mes_de(date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))


def test_filtros_de_template():
    modelo = Template(
        "{% load formato %}{{ valor|brl }} | {{ qtd|inteiro }} | {{ numero|pedido_numero }} | "
        "{{ fracao|pct }} | {{ fracao|pct:2 }} | {{ quando|data_br }} | {{ quando|data_hora_br }}"
        " | {{ nada|brl }}"
    )
    contexto = Context(
        {
            "valor": Decimal("2293.65"),
            "qtd": 1234,
            "numero": 1042,
            "fracao": Decimal("0.3846"),
            "quando": datetime(2026, 11, 1, 1, 30, tzinfo=UTC),
            "nada": None,
        }
    )
    assert modelo.render(contexto) == (
        "R$ 2.293,65 | 1.234 | nº 1.042 | 38,5% | 38,46% | 31/10/2026 | 31/10/2026 22:30 | —"
    )


def test_iniciais_do_avatar():
    modelo = Template("{% load formato %}{{ a|iniciais }} {{ b|iniciais }} [{{ c|iniciais }}]")
    assert modelo.render(Context({"a": "Lucas Tonnon", "b": "carla", "c": ""})) == "LT C []"


def test_texto_em_grupos():
    modelo = Template("{% load formato %}{{ a|em_grupos }} {{ b|em_grupos:3 }} [{{ c|em_grupos }}]")
    contexto = Context({"a": "ABCDEFGHIJ", "b": "123456", "c": ""})
    assert modelo.render(contexto) == "ABCD EFGH IJ 123 456 []"
