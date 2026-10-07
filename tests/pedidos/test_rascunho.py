import re
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction

from apps.cadastros.models import Cliente, Produto
from apps.core.erros import EstoqueInsuficiente, RegraDeNegocio
from apps.pedidos.consultas import avisos_do_rascunho
from apps.pedidos.models import ContadorPedido, Pedido
from apps.pedidos.services import (
    adicionar_item,
    alterar_quantidade,
    criar_rascunho,
    definir_cliente,
    definir_desconto,
    definir_observacoes,
    excluir_rascunho,
    mudar_quantidade,
    pode_editar,
    remover_item,
)
from tests.apoio import com_estoque, criar_cliente, criar_produto, criar_usuario, montar_rascunho

pytestmark = pytest.mark.django_db

NAO_E_RASCUNHO = "Este pedido não é mais um rascunho e não pode ser alterado."


def test_rascunho_nasce_sem_numero(vendedor):
    p = criar_rascunho(vendedor)
    assert (p.status, p.numero, p.criado_por, p.total) == ("rascunho", None, vendedor, Decimal("0"))


def test_adicionar_copia_dados_e_soma_na_mesma_linha(vendedor):
    prod = com_estoque(criar_produto(preco="189.90"), 12)
    p = criar_rascunho(vendedor)
    adicionar_item(p.pk, prod.pk, 2, vendedor)
    item = adicionar_item(p.pk, prod.pk, 3, vendedor)
    assert p.itens.count() == 1 and item.quantidade == 5
    assert (item.codigo, item.descricao, item.preco_unitario) == (
        "CE285A",
        "Toner HP 85A Preto",
        Decimal("189.90"),
    )
    p.refresh_from_db()
    assert p.subtotal == Decimal("949.50") and p.total == Decimal("949.50")


def test_nao_adiciona_alem_do_estoque(vendedor):
    prod = com_estoque(criar_produto(), 12)
    p = criar_rascunho(vendedor)
    with pytest.raises(
        EstoqueInsuficiente, match=re.escape("Estoque insuficiente: 12 em estoque.")
    ):
        adicionar_item(p.pk, prod.pk, 13, vendedor)
    adicionar_item(p.pk, prod.pk, 10, vendedor)
    with pytest.raises(
        EstoqueInsuficiente,
        match=re.escape(
            "Estoque insuficiente: 12 em estoque, 10 já no pedido (dá para adicionar mais 2)."
        ),
    ):
        adicionar_item(p.pk, prod.pk, 3, vendedor)


@pytest.mark.parametrize(
    "qtd,mensagem",
    [
        (0, "Informe uma quantidade inteira maior que zero."),
        (10000, "Quantidade máxima por item: 9.999."),
    ],
)
def test_quantidade_fora_da_faixa(vendedor, qtd, mensagem):
    prod = com_estoque(criar_produto(), 20000)
    with pytest.raises(RegraDeNegocio, match=re.escape(mensagem)):
        adicionar_item(criar_rascunho(vendedor).pk, prod.pk, qtd, vendedor)


@pytest.mark.parametrize("qtd", [-1, True, 1.5, "2", None])
def test_quantidade_precisa_ser_inteira(vendedor, qtd):
    prod = com_estoque(criar_produto(), 5)
    with pytest.raises(RegraDeNegocio, match="Informe uma quantidade inteira maior que zero."):
        adicionar_item(criar_rascunho(vendedor).pk, prod.pk, qtd, vendedor)


def test_somar_na_linha_nao_passa_da_quantidade_maxima(vendedor):
    prod = com_estoque(criar_produto(), 20000)
    p = montar_rascunho(vendedor, itens=[(prod, 9000)])
    with pytest.raises(RegraDeNegocio, match=re.escape("Quantidade máxima por item: 9.999.")):
        adicionar_item(p.pk, prod.pk, 1000, vendedor)
    with pytest.raises(RegraDeNegocio, match=re.escape("Quantidade máxima por item: 9.999.")):
        alterar_quantidade(p.pk, p.itens.get().pk, 10000, vendedor)
    assert p.itens.get().quantidade == 9000


def test_produto_e_cliente_inativos_nao_entram(vendedor):
    prod = criar_produto(ativo=False)
    p = criar_rascunho(vendedor)
    with pytest.raises(
        RegraDeNegocio, match="Este produto está inativo e não pode ser adicionado."
    ):
        adicionar_item(p.pk, prod.pk, 1, vendedor)
    with pytest.raises(RegraDeNegocio, match="Este cliente está inativo. Escolha outro cliente."):
        definir_cliente(p.pk, criar_cliente(ativo=False).pk, vendedor)
    p.refresh_from_db()
    assert p.cliente is None and not p.itens.exists()


def test_definir_cliente(vendedor):
    cli = criar_cliente()
    p = definir_cliente(criar_rascunho(vendedor).pk, cli.pk, vendedor)
    p.refresh_from_db()
    assert p.cliente == cli


def test_aumentar_quantidade_respeita_o_estoque(vendedor):
    prod = com_estoque(criar_produto(), 3)
    p = montar_rascunho(vendedor, itens=[(prod, 3)])
    item = p.itens.get()
    with pytest.raises(
        EstoqueInsuficiente, match="Estoque insuficiente para CE285A: 3 em estoque."
    ):
        alterar_quantidade(p.pk, item.pk, 4, vendedor)
    assert alterar_quantidade(p.pk, item.pk, 1, vendedor).quantidade == 1
    p.refresh_from_db()
    assert p.total == Decimal("189.90")


def test_diminuir_quantidade_vale_mesmo_sem_estoque(vendedor):
    prod = com_estoque(criar_produto(), 5)
    p = montar_rascunho(vendedor, itens=[(prod, 5)])
    Produto.objects.filter(pk=prod.pk).update(estoque=2)
    assert alterar_quantidade(p.pk, p.itens.get().pk, 4, vendedor).quantidade == 4


def test_mudar_quantidade_parte_da_quantidade_gravada(vendedor):  # botões − e + da tela
    prod = com_estoque(criar_produto(), 3)
    p = montar_rascunho(vendedor, itens=[(prod, 2)])
    item = p.itens.get()
    assert mudar_quantidade(p.pk, item.pk, 1, vendedor).quantidade == 3
    with pytest.raises(
        EstoqueInsuficiente, match="Estoque insuficiente para CE285A: 3 em estoque."
    ):
        mudar_quantidade(p.pk, item.pk, 1, vendedor)
    assert mudar_quantidade(p.pk, item.pk, -1, vendedor).quantidade == 2
    assert mudar_quantidade(p.pk, item.pk, -1, vendedor).quantidade == 1
    with pytest.raises(RegraDeNegocio, match="Informe uma quantidade inteira maior que zero."):
        mudar_quantidade(p.pk, item.pk, -1, vendedor)
    p.refresh_from_db()
    assert (p.itens.get().quantidade, p.total) == (1, Decimal("189.90"))


def test_observacoes_sem_caractere_nulo(vendedor):  # Ruling R23: o PostgreSQL recusa o NUL
    p = definir_observacoes(criar_rascunho(vendedor).pk, " a\x00b ", vendedor)
    p.refresh_from_db()
    assert p.observacoes == "ab"


def test_mudar_quantidade_de_item_removido_ou_de_outra_pessoa(vendedor, administrador):
    p = montar_rascunho(vendedor, itens=[(com_estoque(criar_produto(), 5), 2)])
    item = p.itens.get()
    with pytest.raises(PermissionDenied):
        mudar_quantidade(p.pk, item.pk, 1, criar_usuario(email="outro@helptoner.com.br"))
    assert mudar_quantidade(p.pk, item.pk, 1, administrador).quantidade == 3
    remover_item(p.pk, item.pk, vendedor)
    with pytest.raises(RegraDeNegocio, match="Este item não está mais no pedido."):
        mudar_quantidade(p.pk, item.pk, 1, vendedor)


def test_remover_item_que_deixa_desconto_maior_que_o_subtotal(vendedor):  # Review Focus 4
    a = com_estoque(criar_produto("CE285A", preco="189.90"), 5)
    b = com_estoque(criar_produto("TN-1060", preco="89.90"), 5)
    p = montar_rascunho(vendedor, itens=[(a, 1), (b, 1)], desconto=("reais", "100"))
    remover_item(p.pk, p.itens.get(produto=a).pk, vendedor)
    p.refresh_from_db()
    assert (p.desconto_informado, p.desconto_valor, p.total) == (
        Decimal("100.00"),
        Decimal("0.00"),
        Decimal("89.90"),
    )
    assert avisos_do_rascunho(p).erro_desconto == "O desconto não pode passar do subtotal."


def test_item_removido_em_outra_aba(vendedor):
    prod = com_estoque(criar_produto(), 5)
    p = montar_rascunho(vendedor, itens=[(prod, 2)])
    item = p.itens.get()
    remover_item(p.pk, item.pk, vendedor)
    remover_item(p.pk, item.pk, vendedor)  # o segundo clique não dá erro
    with pytest.raises(RegraDeNegocio, match="Este item não está mais no pedido."):
        alterar_quantidade(p.pk, item.pk, 3, vendedor)
    p.refresh_from_db()
    assert (p.itens.count(), p.total) == (0, Decimal("0.00"))


def test_avisos_de_estoque_e_de_inativos(vendedor):
    prod = com_estoque(criar_produto(), 5)
    cli = criar_cliente()
    p = montar_rascunho(vendedor, cliente=cli, itens=[(prod, 5)])
    Produto.objects.filter(pk=prod.pk).update(estoque=3)
    Cliente.objects.filter(pk=cli.pk).update(ativo=False)
    av = avisos_do_rascunho(p)
    assert av.por_item[p.itens.get().pk] == "Só há 3 em estoque."
    assert av.gerais == ["O cliente Papelaria Central Ltda foi inativado. Escolha outro cliente."]


def test_avisos_de_produto_inativo_e_sem_estoque(vendedor):
    a = com_estoque(criar_produto("CE285A"), 5)
    b = com_estoque(criar_produto("TN-1060"), 5)
    c = com_estoque(criar_produto("CF217A"), 5)
    p = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(a, 1), (b, 1), (c, 1)])
    Produto.objects.filter(pk=a.pk).update(ativo=False, estoque=0)
    Produto.objects.filter(pk=b.pk).update(estoque=0)
    av = avisos_do_rascunho(p)
    assert av.por_item == {
        p.itens.get(produto=a).pk: "O produto CE285A foi inativado. Remova-o do pedido.",
        p.itens.get(produto=b).pk: "Sem estoque.",
    }
    assert (av.gerais, av.erro_desconto) == ([], None)


def test_desconto_valido_e_gravado(vendedor):
    prod = com_estoque(criar_produto(preco="189.90"), 5)
    p = montar_rascunho(vendedor, itens=[(prod, 1)])
    p = definir_desconto(p.pk, "percentual", Decimal("10"), vendedor)
    p.refresh_from_db()
    assert (p.desconto_tipo, p.desconto_informado, p.desconto_valor, p.total) == (
        "percentual",
        Decimal("10.00"),
        Decimal("18.99"),
        Decimal("170.91"),
    )


def test_desconto_invalido_nao_grava(vendedor):
    p = criar_rascunho(vendedor)
    with pytest.raises(RegraDeNegocio, match="O desconto não pode passar de 100%."):
        definir_desconto(p.pk, "percentual", Decimal("101"), vendedor)


@pytest.mark.parametrize(
    "tipo,valor,mensagem",
    [
        ("reais", Decimal("-1"), "O desconto não pode ser negativo."),
        ("dolar", Decimal("1"), "Tipo de desconto inválido."),
        ("reais", Decimal("NaN"), "Informe um número. Ex.: 10 ou 10,5"),
        ("reais", Decimal("1e20"), "O desconto não pode passar do subtotal."),
    ],
)
def test_desconto_recusado_nao_muda_o_rascunho(vendedor, tipo, valor, mensagem):
    prod = com_estoque(criar_produto(preco="189.90"), 5)
    p = montar_rascunho(vendedor, itens=[(prod, 1)], desconto=("reais", "10"))
    with pytest.raises(RegraDeNegocio, match=re.escape(mensagem)):
        definir_desconto(p.pk, tipo, valor, vendedor)
    p.refresh_from_db()
    assert (p.desconto_tipo, p.desconto_informado, p.total) == (
        "reais",
        Decimal("10.00"),
        Decimal("179.90"),
    )


def test_desconto_em_reais_maior_que_o_subtotal_fica_salvo_com_aviso(vendedor):  # Decisão P3
    prod = com_estoque(criar_produto(preco="89.90"), 5)
    p = montar_rascunho(vendedor, itens=[(prod, 1)])
    definir_desconto(p.pk, "reais", Decimal("100"), vendedor)
    p.refresh_from_db()
    assert (p.desconto_informado, p.desconto_valor, p.total) == (
        Decimal("100.00"),
        Decimal("0.00"),
        Decimal("89.90"),
    )
    assert avisos_do_rascunho(p).erro_desconto == "O desconto não pode passar do subtotal."


def test_so_quem_criou_ou_administrador_edita(vendedor, administrador):
    p = criar_rascunho(vendedor)
    outro = criar_usuario(email="outro@helptoner.com.br")
    with pytest.raises(PermissionDenied):
        definir_observacoes(p.pk, "x", outro)
    assert (
        definir_observacoes(p.pk, "entregar na portaria", administrador).observacoes
        == "entregar na portaria"
    )
    with pytest.raises(RegraDeNegocio, match="As observações podem ter até 1.000 caracteres."):
        definir_observacoes(p.pk, "x" * 1001, vendedor)
    p.refresh_from_db()
    assert p.observacoes == "entregar na portaria"


def test_pode_editar(vendedor, administrador):
    p = criar_rascunho(vendedor)
    outro = criar_usuario(email="outro@helptoner.com.br")
    assert (pode_editar(p, vendedor), pode_editar(p, administrador), pode_editar(p, outro)) == (
        True,
        True,
        False,
    )
    Pedido.objects.filter(pk=p.pk).update(status="confirmado", numero=1)
    p.refresh_from_db()
    assert not pode_editar(p, vendedor) and not pode_editar(p, administrador)


def test_pedido_que_nao_e_mais_rascunho_nao_muda(vendedor):
    prod = com_estoque(criar_produto(), 5)
    p = montar_rascunho(vendedor, itens=[(prod, 1)])
    Pedido.objects.filter(pk=p.pk).update(status="confirmado", numero=1)
    with pytest.raises(RegraDeNegocio, match=NAO_E_RASCUNHO):
        adicionar_item(p.pk, prod.pk, 1, vendedor)
    with pytest.raises(RegraDeNegocio, match=NAO_E_RASCUNHO):
        excluir_rascunho(p.pk, vendedor)
    assert Pedido.objects.filter(pk=p.pk).exists() and p.itens.get().quantidade == 1


def test_excluir_rascunho(vendedor):
    p = criar_rascunho(vendedor)
    excluir_rascunho(p.pk, vendedor)
    assert not Pedido.objects.filter(pk=p.pk).exists()


def test_vendedor_nao_exclui_rascunho_de_outro(vendedor):
    p = criar_rascunho(criar_usuario(email="outro@helptoner.com.br"))
    with pytest.raises(PermissionDenied):
        excluir_rascunho(p.pk, vendedor)
    assert Pedido.objects.filter(pk=p.pk).exists()


def test_numero_so_fora_do_rascunho(vendedor):
    p = criar_rascunho(vendedor)
    with pytest.raises(IntegrityError), transaction.atomic():
        Pedido.objects.filter(pk=p.pk).update(numero=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Pedido.objects.filter(pk=p.pk).update(status="confirmado")


def test_contador_nasce_da_migracao():
    assert list(ContadorPedido.objects.values_list("pk", "ultimo_numero")) == [(1, 0)]
