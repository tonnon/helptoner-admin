from decimal import Decimal

import pytest

from apps.cadastros.models import Cliente, Produto
from apps.core.erros import RegraDeNegocio
from apps.pedidos.consultas import avisos_do_rascunho
from apps.pedidos.models import ContadorPedido, Pedido
from apps.pedidos.services import cancelar_pedido, criar_rascunho, repetir_pedido
from tests.apoio import (
    com_estoque,
    criar_cliente,
    criar_produto,
    criar_usuario,
    montar_pedido_confirmado,
)

pytestmark = pytest.mark.django_db


def test_repetir_usa_precos_e_descricoes_atuais(vendedor):
    prod = com_estoque(criar_produto(preco="179.90"), 10)
    original = montar_pedido_confirmado(vendedor, itens=[(prod, 2)], desconto=("percentual", "10"))
    Produto.objects.filter(pk=prod.pk).update(
        preco=Decimal("189.90"), descricao="Toner HP 85A Preto (novo)"
    )
    outro = criar_usuario(email="outro@helptoner.com.br")
    novo = repetir_pedido(original.pk, outro)
    item = novo.itens.get()
    assert (
        novo.status,
        novo.cliente,
        novo.criado_por,
        novo.desconto_informado,
        novo.observacoes,
    ) == ("rascunho", original.cliente, outro, Decimal("0"), "")
    assert (item.quantidade, item.preco_unitario, item.descricao) == (
        2,
        Decimal("189.90"),
        "Toner HP 85A Preto (novo)",
    )
    assert novo.subtotal == Decimal("379.80")
    original.refresh_from_db()
    assert original.itens.get().preco_unitario == Decimal("179.90")


def test_repetir_grava_o_rascunho_sem_numero_desconto_nem_observacoes(vendedor):
    p1 = com_estoque(criar_produto("CE285A", preco="100.00"), 10)
    p2 = com_estoque(criar_produto("TN-1060", descricao="Toner Brother TN-1060", preco="50.00"), 10)
    original = montar_pedido_confirmado(
        vendedor, itens=[(p2, 1), (p1, 3)], desconto=("reais", "20")
    )
    Pedido.objects.filter(pk=original.pk).update(observacoes="Entregar na portaria")
    Produto.objects.filter(pk=p1.pk).update(codigo="CE285AX")
    novo = Pedido.objects.get(pk=repetir_pedido(original.pk, vendedor).pk)
    assert (novo.numero, novo.status, novo.confirmado_por, novo.observacoes) == (
        None,
        "rascunho",
        None,
        "",
    )
    assert (novo.desconto_valor, novo.subtotal, novo.total) == (
        Decimal("0.00"),
        Decimal("350.00"),
        Decimal("350.00"),
    )
    # Os itens vêm na ordem do pedido original, com o código atual e ainda sem custo.
    assert [
        (i.produto, i.codigo, i.quantidade, i.preco_unitario, i.custo_unitario)
        for i in novo.itens.all()
    ] == [
        (p2, "TN-1060", 1, Decimal("50.00"), None),
        (p1, "CE285AX", 3, Decimal("100.00"), None),
    ]
    assert ContadorPedido.objects.get().ultimo_numero == 1


def test_repetir_traz_itens_inativos_ou_sem_estoque_com_aviso(vendedor):
    """Decisão P7: o rascunho nasce com tudo e os avisos mostram o que impede a confirmação."""
    cliente = criar_cliente()
    inativo = com_estoque(criar_produto("CE285A"), 5)
    vai_acabar = com_estoque(criar_produto("TN-1060", descricao="Toner Brother TN-1060"), 3)
    original = montar_pedido_confirmado(
        vendedor, cliente=cliente, itens=[(inativo, 2), (vai_acabar, 3)]
    )
    Produto.objects.filter(pk=inativo.pk).update(ativo=False)
    Cliente.objects.filter(pk=cliente.pk).update(ativo=False)
    novo = repetir_pedido(original.pk, vendedor)
    i1, i2 = novo.itens.all()
    avisos = avisos_do_rascunho(novo)
    assert avisos.gerais == [
        "O cliente Papelaria Central Ltda foi inativado. Escolha outro cliente."
    ]
    assert avisos.por_item == {
        i1.pk: "O produto CE285A foi inativado. Remova-o do pedido.",
        i2.pk: "Sem estoque.",
    }


def test_repetir_funciona_para_cancelado_e_nao_para_rascunho(vendedor, administrador):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    cancelar_pedido(ped.pk, "Cliente desistiu", administrador)
    assert repetir_pedido(ped.pk, vendedor).status == "rascunho"
    with pytest.raises(
        RegraDeNegocio, match="Só pedidos confirmados ou cancelados podem ser repetidos."
    ):
        repetir_pedido(criar_rascunho(vendedor).pk, vendedor)
