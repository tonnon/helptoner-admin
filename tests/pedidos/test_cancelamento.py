import itertools
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.contas.models import ADMINISTRADOR
from apps.core.erros import RegraDeNegocio
from apps.estoque.models import MovimentoEstoque
from apps.estoque.services import registrar_entrada
from apps.pedidos import services
from apps.pedidos.models import Pedido
from apps.pedidos.services import cancelar_pedido, criar_rascunho
from tests.apoio import (
    com_estoque,
    criar_produto,
    criar_usuario,
    esperar_conexao_presa,
    montar_pedido_confirmado,
    rodar_juntos,
)

pytestmark = pytest.mark.django_db

concorrencia = pytest.mark.django_db(transaction=True, serialized_rollback=True)

SO_CONFIRMADOS = "Só pedidos confirmados podem ser cancelados."


def test_cancelar_devolve_o_estoque_pelo_custo_gravado(administrador, vendedor):
    prod = com_estoque(criar_produto(), 10, "60.00", por=administrador)
    ped = montar_pedido_confirmado(vendedor, itens=[(prod, 2)])  # sai com custo 60
    registrar_entrada(
        produto_id=prod.pk,
        quantidade=8,
        custo_unitario=Decimal("80.00"),
        observacao="NF 9",
        usuario=administrador,
    )
    ped = cancelar_pedido(ped.pk, "Cliente desistiu", administrador)  # estoque 16 a 70,0000
    prod.refresh_from_db()
    assert (prod.estoque, prod.custo_medio) == (18, Decimal("68.8889"))  # (16×70 + 2×60) ÷ 18
    assert (ped.status, ped.cancelado_por, ped.motivo_cancelamento) == (
        "cancelado",
        administrador,
        "Cliente desistiu",
    )
    dev = MovimentoEstoque.objects.get(tipo="devolucao")
    assert (dev.quantidade, dev.custo_unitario, dev.pedido) == (2, Decimal("60.0000"), ped)


def test_cancelar_grava_quem_quando_e_o_motivo_sem_espacos(administrador, vendedor):
    prod = com_estoque(criar_produto(), 10, por=administrador)
    ped = montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    cancelar_pedido(ped.pk, "  Cliente desistiu \n", administrador)
    ped = Pedido.objects.get(pk=ped.pk)
    assert (ped.status, ped.cancelado_por, ped.motivo_cancelamento) == (
        "cancelado",
        administrador,
        "Cliente desistiu",
    )
    assert ped.cancelado_em > ped.confirmado_em
    # Número, totais e itens do pedido continuam como na confirmação.
    assert (ped.numero, ped.total, ped.itens.get().custo_unitario) == (
        1,
        Decimal("189.90"),
        Decimal("100.0000"),
    )


def test_cancelar_devolve_cada_item_pelo_seu_custo(administrador, vendedor):
    p1 = com_estoque(criar_produto("CE285A"), 10, "60.00", por=administrador)
    p2 = com_estoque(criar_produto("TN-1060", descricao="Toner Brother TN-1060"), 5, "20.00")
    ped = montar_pedido_confirmado(vendedor, itens=[(p1, 3), (p2, 2)])
    cancelar_pedido(ped.pk, "Pedido em duplicidade", administrador)
    p1.refresh_from_db()
    p2.refresh_from_db()
    assert (p1.estoque, p1.custo_medio, p2.estoque, p2.custo_medio) == (
        10,
        Decimal("60.0000"),
        5,
        Decimal("20.0000"),
    )
    devolucoes = MovimentoEstoque.objects.filter(tipo="devolucao").order_by("produto_id")
    assert [
        (m.produto, m.quantidade, m.custo_unitario, m.estoque_apos, m.usuario, m.pedido)
        for m in devolucoes
    ] == [
        (p1, 3, Decimal("60.0000"), 10, administrador, ped),
        (p2, 2, Decimal("20.0000"), 5, administrador, ped),
    ]


def test_cancelamento_exige_administrador_motivo_e_pedido_confirmado(vendedor, administrador):
    prod = com_estoque(criar_produto(), 10)
    ped = montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    with pytest.raises(PermissionDenied):
        cancelar_pedido(ped.pk, "x", vendedor)
    with pytest.raises(RegraDeNegocio, match="Informe o motivo do cancelamento."):
        cancelar_pedido(ped.pk, "  ", administrador)
    with pytest.raises(RegraDeNegocio, match=SO_CONFIRMADOS):
        cancelar_pedido(criar_rascunho(vendedor).pk, "x", administrador)
    ped.refresh_from_db()
    assert ped.status == "confirmado"
    assert not MovimentoEstoque.objects.filter(tipo="devolucao").exists()


def test_pedido_cancelado_nao_e_cancelado_de_novo(administrador, vendedor):
    prod = com_estoque(criar_produto(), 10)
    ped = montar_pedido_confirmado(vendedor, itens=[(prod, 2)])
    cancelar_pedido(ped.pk, "Cliente desistiu", administrador)
    with pytest.raises(RegraDeNegocio, match=SO_CONFIRMADOS):
        cancelar_pedido(ped.pk, "De novo", administrador)
    prod.refresh_from_db()
    assert prod.estoque == 10
    assert Pedido.objects.get(pk=ped.pk).motivo_cancelamento == "Cliente desistiu"


def test_cancelar_trava_o_pedido_e_depois_os_produtos_em_ordem_de_id(administrador, vendedor):
    """Mesma ordem de travas da confirmação (§3.1): sem ela, as duas se travariam em cruz."""
    menor = com_estoque(criar_produto("CE285A"), 10)
    maior = com_estoque(criar_produto("TN-1060", descricao="Toner Brother TN-1060"), 10)
    ped = montar_pedido_confirmado(vendedor, itens=[(maior, 1), (menor, 1)])
    with CaptureQueriesContext(connection) as feitas:
        cancelar_pedido(ped.pk, "x", administrador)
    travas = [q["sql"] for q in feitas.captured_queries if " FOR " in q["sql"]]
    assert len(travas) == 2, travas
    assert 'FROM "pedidos_pedido"' in travas[0] and travas[0].endswith(" FOR UPDATE")
    assert 'FROM "cadastros_produto"' in travas[1]
    assert travas[1].endswith(' ORDER BY "cadastros_produto"."id" ASC FOR NO KEY UPDATE')


@pytest.fixture
def disputa(monkeypatch):
    """Garante a disputa: o cancelamento que trava o pedido primeiro espera o outro ficar preso.

    A devolução roda com o pedido e os produtos já travados.
    """
    devolver = services.registrar_devolucao_pedido
    chamadas = itertools.count()

    def com_o_outro_preso(**dados):
        if next(chamadas) == 0:
            esperar_conexao_presa()
        return devolver(**dados)

    monkeypatch.setattr(services, "registrar_devolucao_pedido", com_o_outro_preso)


@concorrencia
def test_cancelar_duas_vezes_ao_mesmo_tempo_devolve_uma_vez(disputa):  # Review Focus 2
    adm = criar_usuario(ADMINISTRADOR)
    prod = com_estoque(criar_produto(), 10, por=adm)
    ped = montar_pedido_confirmado(adm, itens=[(prod, 2)])
    resultados = rodar_juntos(
        lambda: cancelar_pedido(ped.pk, "a", adm), lambda: cancelar_pedido(ped.pk, "b", adm)
    )
    cancelados = [r for r in resultados if isinstance(r, Pedido)]
    recusas = [r for r in resultados if isinstance(r, RegraDeNegocio)]
    assert len(cancelados) == 1 and len(recusas) == 1, resultados
    assert recusas[0].mensagem == SO_CONFIRMADOS
    prod.refresh_from_db()
    assert prod.estoque == 10 and MovimentoEstoque.objects.filter(tipo="devolucao").count() == 1
    assert Pedido.objects.get(pk=ped.pk).motivo_cancelamento == cancelados[0].motivo_cancelamento


def test_motivo_acima_de_500_caracteres_e_recusado(administrador, vendedor):
    pedido = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    with pytest.raises(RegraDeNegocio, match="O motivo pode ter até 500 caracteres."):
        cancelar_pedido(pedido.pk, "x" * 501, administrador)
    pedido.refresh_from_db()
    assert pedido.status == Pedido.Status.CONFIRMADO
    cancelar_pedido(pedido.pk, "  " + "x" * 500 + "  ", administrador)
