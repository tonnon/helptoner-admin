import time

import pytest

from apps.core.erros import EstoqueInsuficiente
from apps.pedidos import services
from apps.pedidos.services import adicionar_item, criar_rascunho
from tests.apoio import com_estoque, criar_produto, criar_usuario, rodar_juntos

concorrencia = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@pytest.fixture
def trava_demorada(monkeypatch):
    """Segura a trava do pedido por um instante, para a outra aba chegar a ela com certeza."""
    recalcular = services._recalcular

    def devagar(pedido):
        time.sleep(0.3)
        return recalcular(pedido)

    monkeypatch.setattr(services, "_recalcular", devagar)


@concorrencia
def test_mesmo_produto_em_duas_abas_soma_na_linha(trava_demorada):  # Review Focus 2
    vendedor = criar_usuario()
    prod = com_estoque(criar_produto(), 10)
    p = criar_rascunho(vendedor)
    resultados = rodar_juntos(
        lambda: adicionar_item(p.pk, prod.pk, 2, vendedor),
        lambda: adicionar_item(p.pk, prod.pk, 3, vendedor),
    )
    assert not any(isinstance(r, Exception) for r in resultados)
    assert p.itens.get().quantidade == 5


@concorrencia
def test_duas_abas_juntas_nao_passam_do_estoque(trava_demorada):
    vendedor = criar_usuario()
    prod = com_estoque(criar_produto(), 4)
    p = criar_rascunho(vendedor)
    resultados = rodar_juntos(
        lambda: adicionar_item(p.pk, prod.pk, 3, vendedor),
        lambda: adicionar_item(p.pk, prod.pk, 3, vendedor),
    )
    recusas = [r for r in resultados if isinstance(r, EstoqueInsuficiente)]
    assert [r.mensagem for r in recusas] == [
        "Estoque insuficiente: 4 em estoque, 3 já no pedido (dá para adicionar mais 1)."
    ]
    assert p.itens.get().quantidade == 3


def test_rodar_juntos_devolve_resultados_e_excecoes_na_ordem():
    resultados = rodar_juntos(lambda: 1, lambda: 1 / 0, lambda: "três")
    assert resultados[0] == 1 and isinstance(resultados[1], ZeroDivisionError)
    assert resultados[2] == "três"
