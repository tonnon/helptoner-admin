import itertools
import threading

import pytest
from django.db import DatabaseError, transaction

from apps.cadastros.models import Produto
from apps.core.erros import RegraDeNegocio
from apps.estoque.models import MovimentoEstoque
from apps.pedidos import services
from apps.pedidos.models import ContadorPedido, Pedido
from apps.pedidos.services import ConfirmacaoRecusada, confirmar_pedido
from tests.apoio import (
    com_estoque,
    criar_cliente,
    criar_produto,
    criar_usuario,
    esperar_conexao_presa,
    montar_rascunho,
    rodar_juntos,
)

concorrencia = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@pytest.fixture
def disputa(monkeypatch):
    """Garante a disputa: a confirmação que pega as travas primeiro espera a outra ficar presa.

    `_recalcular` roda com o pedido e os produtos já travados. Chame `disputa()` depois de montar
    os rascunhos, porque os serviços do rascunho também usam `_recalcular`.
    """

    def armar():
        recalcular = services._recalcular
        chamadas = itertools.count()

        def com_a_outra_presa(pedido):
            if next(chamadas) == 0:
                esperar_conexao_presa()
            return recalcular(pedido)

        monkeypatch.setattr(services, "_recalcular", com_a_outra_presa)

    return armar


@concorrencia
def test_duas_confirmacoes_disputando_o_estoque(disputa):
    v = criar_usuario()
    prod = com_estoque(criar_produto(), 10)
    cli = criar_cliente()
    a, b = (montar_rascunho(v, cliente=cli, itens=[(prod, 8)]) for _ in range(2))
    disputa()
    resultados = rodar_juntos(lambda: confirmar_pedido(a.pk, v), lambda: confirmar_pedido(b.pk, v))
    recusas = [r for r in resultados if isinstance(r, ConfirmacaoRecusada)]
    assert len(recusas) == 1, resultados
    assert recusas[0].motivos == ["Estoque insuficiente para CE285A: 2 em estoque, 8 no pedido."]
    assert sum(isinstance(r, Pedido) for r in resultados) == 1
    prod.refresh_from_db()
    assert prod.estoque == 2 and ContadorPedido.objects.get().ultimo_numero == 1


@concorrencia
def test_mesmo_rascunho_confirmado_duas_vezes_ao_mesmo_tempo(disputa):  # Review Focus 2
    v = criar_usuario()
    prod = com_estoque(criar_produto(), 10)
    ped = montar_rascunho(v, cliente=criar_cliente(), itens=[(prod, 1)])
    disputa()
    resultados = rodar_juntos(
        lambda: confirmar_pedido(ped.pk, v), lambda: confirmar_pedido(ped.pk, v)
    )
    assert sum(isinstance(r, Pedido) for r in resultados) == 1, resultados
    assert any(
        isinstance(r, RegraDeNegocio) and "não é mais um rascunho" in r.mensagem for r in resultados
    )
    assert MovimentoEstoque.objects.filter(tipo="saida").count() == 1
    assert ContadorPedido.objects.get().ultimo_numero == 1


def _livre(produto) -> bool:
    """Se a linha do produto pode ser travada agora, sem esperar ninguém."""
    try:
        with transaction.atomic():
            Produto.objects.select_for_update(nowait=True).get(pk=produto.pk)
    except DatabaseError:
        return False
    return True


@concorrencia
def test_produtos_sao_travados_em_ordem_de_id():  # §3.1, passo 1
    """Presa no produto de id menor, a confirmação ainda não pode segurar o de id maior.

    Se travasse na ordem dos itens (o de id maior primeiro), outra confirmação com os mesmos
    produtos na ordem inversa ficaria presa em cruz com ela.
    """
    v = criar_usuario()
    menor = com_estoque(criar_produto("CE285A"), 10)
    maior = com_estoque(criar_produto("TN-1060", descricao="Toner Brother TN-1060"), 10)
    assert menor.pk < maior.pk
    ped = montar_rascunho(v, cliente=criar_cliente(), itens=[(maior, 1), (menor, 1)])
    menor_travado = threading.Event()

    def segurar_o_menor():
        with transaction.atomic():
            Produto.objects.select_for_update().get(pk=menor.pk)
            menor_travado.set()
            esperar_conexao_presa()
            return _livre(maior)

    def confirmar():
        assert menor_travado.wait(10), "O produto de id menor não foi travado."
        return confirmar_pedido(ped.pk, v)

    maior_livre, confirmado = rodar_juntos(segurar_o_menor, confirmar)
    assert maior_livre is True, maior_livre
    assert isinstance(confirmado, Pedido), confirmado
