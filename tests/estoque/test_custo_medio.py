from decimal import Decimal

import pytest

from apps.estoque.services import novo_custo_medio


@pytest.mark.parametrize(
    "estoque,custo,qtd,entrada,esperado",
    [
        (10, "60", 10, "80", "70.0000"),
        (0, "55.5", 4, "80", "80.0000"),
        (7, "10", 3, "20", "13.0000"),
        (2, "10", 1, "11", "10.3333"),
    ],
)
def test_formula_do_custo_medio(estoque, custo, qtd, entrada, esperado):
    assert novo_custo_medio(estoque, Decimal(custo), qtd, Decimal(entrada)) == Decimal(esperado)
