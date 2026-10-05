from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from apps.cadastros.models import Cliente, Produto
from apps.core.erros import RegraDeNegocio
from apps.estoque.models import MovimentoEstoque
from apps.pedidos.models import ContadorPedido, Pedido
from apps.pedidos.services import (
    ConfirmacaoRecusada,
    MudancaPreco,
    PrecosAlterados,
    confirmar_pedido,
)
from tests.apoio import (
    com_estoque,
    criar_cliente,
    criar_produto,
    criar_usuario,
    montar_pedido_confirmado,
    montar_rascunho,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def dois_produtos(administrador):
    return (
        com_estoque(criar_produto("CE285A", preco="100.00"), 10, "60.00", por=administrador),
        com_estoque(
            criar_produto(
                "TN-1060", descricao="Toner Brother TN-1060", marca="Brother", preco="50.00"
            ),
            10,
            "20.00",
            por=administrador,
        ),
    )


def test_confirmar_grava_numero_custo_baixa_rateio_e_totais(vendedor, dois_produtos):
    p1, p2 = dois_produtos
    ped = montar_rascunho(
        vendedor, cliente=criar_cliente(), itens=[(p1, 2), (p2, 1)], desconto=("percentual", "10")
    )
    ped = confirmar_pedido(ped.pk, vendedor)
    assert (ped.numero, ped.status, ped.confirmado_por) == (1, "confirmado", vendedor)
    assert ped.confirmado_em
    assert (ped.subtotal, ped.desconto_valor, ped.total) == (
        Decimal("250.00"),
        Decimal("25.00"),
        Decimal("225.00"),
    )
    i1, i2 = ped.itens.order_by("id")
    assert (i1.custo_unitario, i2.custo_unitario) == (Decimal("60.0000"), Decimal("20.0000"))
    assert (i1.desconto_rateado, i2.desconto_rateado) == (Decimal("20.00"), Decimal("5.00"))
    p1.refresh_from_db()
    saida = MovimentoEstoque.objects.get(produto=p1, tipo="saida")
    assert (p1.estoque, saida.quantidade, saida.pedido, saida.estoque_apos) == (8, 2, ped, 8)
    assert saida.usuario == vendedor
    # A saída não muda o custo médio (§3.5).
    assert saida.custo_unitario == saida.custo_medio_apos == p1.custo_medio == Decimal("60.0000")
    p2.refresh_from_db()
    assert p2.estoque == 9


def test_numeracao_sem_buracos(vendedor, dois_produtos):
    p1, _ = dois_produtos
    cli = criar_cliente()
    primeiro = montar_rascunho(vendedor, cliente=cli, itens=[(p1, 1)])
    assert confirmar_pedido(primeiro.pk, vendedor).numero == 1
    falha = montar_rascunho(vendedor, cliente=cli, itens=[(p1, 1)])
    Produto.objects.filter(pk=p1.pk).update(estoque=0)
    with pytest.raises(ConfirmacaoRecusada):
        confirmar_pedido(falha.pk, vendedor)
    Produto.objects.filter(pk=p1.pk).update(estoque=5)
    assert confirmar_pedido(falha.pk, vendedor).numero == 2
    assert ContadorPedido.objects.get().ultimo_numero == 2


def test_preco_alterado_atualiza_o_rascunho_e_nao_confirma(vendedor):
    prod = com_estoque(criar_produto(preco="179.90"), 10)
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(prod, 1)])
    prod.preco = Decimal("189.90")
    prod.save()
    with pytest.raises(
        PrecosAlterados,
        match="Os preços de alguns produtos mudaram. Confira o novo total e confirme de novo.",
    ) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.mudancas == [
        MudancaPreco("CE285A", "Toner HP 85A Preto", Decimal("179.90"), Decimal("189.90"))
    ]
    ped.refresh_from_db()
    prod.refresh_from_db()
    assert (ped.status, ped.numero, ped.subtotal, ped.itens.get().preco_unitario, prod.estoque) == (
        "rascunho",
        None,
        Decimal("189.90"),
        Decimal("189.90"),
        10,
    )
    assert ped.total == Decimal("189.90") and ContadorPedido.objects.get().ultimo_numero == 0
    assert not MovimentoEstoque.objects.filter(tipo="saida").exists()
    assert confirmar_pedido(ped.pk, vendedor).numero == 1


def test_so_os_itens_com_preco_novo_aparecem_nas_mudancas(vendedor, dois_produtos):
    p1, p2 = dois_produtos
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(p1, 2), (p2, 1)])
    Produto.objects.filter(pk=p2.pk).update(preco=Decimal("45.00"))
    with pytest.raises(PrecosAlterados) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.mudancas == [
        MudancaPreco("TN-1060", "Toner Brother TN-1060", Decimal("50.00"), Decimal("45.00"))
    ]
    ped.refresh_from_db()
    assert [i.preco_unitario for i in ped.itens.order_by("id")] == [
        Decimal("100.00"),
        Decimal("45.00"),
    ]
    assert ped.subtotal == Decimal("245.00")


def test_preco_menor_que_deixa_o_desconto_maior_que_o_subtotal(vendedor):  # Review Focus 4
    prod = com_estoque(criar_produto(preco="179.90"), 10)
    ped = montar_rascunho(
        vendedor, cliente=criar_cliente(), itens=[(prod, 1)], desconto=("reais", "150")
    )
    Produto.objects.filter(pk=prod.pk).update(preco=Decimal("100.00"))
    with pytest.raises(PrecosAlterados):
        confirmar_pedido(ped.pk, vendedor)
    with pytest.raises(ConfirmacaoRecusada, match="O desconto não pode passar do subtotal."):
        confirmar_pedido(ped.pk, vendedor)
    ped.refresh_from_db()
    assert (ped.status, ped.numero) == ("rascunho", None)
    assert not MovimentoEstoque.objects.filter(tipo="saida").exists()


@pytest.mark.parametrize(
    "cenario,motivo",
    [
        (
            "cliente_inativo",
            "O cliente Papelaria Central Ltda foi inativado. Escolha outro cliente.",
        ),
        ("produto_inativo", "O produto CE285A foi inativado. Remova-o do pedido."),
        ("sem_cliente", "Escolha o cliente antes de confirmar."),
        ("sem_itens", "Adicione pelo menos um produto."),
        ("sem_estoque", "Estoque insuficiente para CE285A: 2 em estoque, 8 no pedido."),
    ],
)
def test_confirmacao_recusada_nao_muda_nada(vendedor, cenario, motivo):
    prod = com_estoque(criar_produto(), 10)
    cli = criar_cliente("Papelaria Central Ltda")
    ped = montar_rascunho(vendedor, cliente=cli, itens=[(prod, 8)])
    match cenario:
        case "cliente_inativo":
            Cliente.objects.filter(pk=cli.pk).update(ativo=False)
        case "produto_inativo":
            Produto.objects.filter(pk=prod.pk).update(ativo=False)
        case "sem_cliente":
            Pedido.objects.filter(pk=ped.pk).update(cliente=None)
        case "sem_itens":
            ped.itens.all().delete()
        case "sem_estoque":
            Produto.objects.filter(pk=prod.pk).update(estoque=2)
    estoque_antes = Produto.objects.get(pk=prod.pk).estoque
    with pytest.raises(ConfirmacaoRecusada) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.motivos == [motivo] and erro.value.mensagem == motivo
    ped.refresh_from_db()
    assert (ped.status, ped.numero) == ("rascunho", None)
    assert Produto.objects.get(pk=prod.pk).estoque == estoque_antes
    assert ContadorPedido.objects.get().ultimo_numero == 0
    assert not MovimentoEstoque.objects.filter(tipo="saida").exists()


def test_recusa_junta_todos_os_motivos_da_mesma_etapa(vendedor, dois_produtos):
    p1, p2 = dois_produtos
    cli = criar_cliente("Papelaria Central Ltda")
    ped = montar_rascunho(vendedor, cliente=cli, itens=[(p1, 1), (p2, 1)])
    Cliente.objects.filter(pk=cli.pk).update(ativo=False)
    Produto.objects.filter(pk__in=[p1.pk, p2.pk]).update(ativo=False)
    with pytest.raises(ConfirmacaoRecusada) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.motivos == [
        "O cliente Papelaria Central Ltda foi inativado. Escolha outro cliente.",
        "O produto CE285A foi inativado. Remova-o do pedido.",
        "O produto TN-1060 foi inativado. Remova-o do pedido.",
    ]
    assert erro.value.mensagem == " ".join(erro.value.motivos)


def test_falta_de_estoque_e_desconto_invalido_saem_juntos(vendedor):
    prod = com_estoque(criar_produto(preco="100.00"), 10)
    ped = montar_rascunho(
        vendedor, cliente=criar_cliente(), itens=[(prod, 8)], desconto=("reais", "5000")
    )
    Produto.objects.filter(pk=prod.pk).update(estoque=2)
    with pytest.raises(ConfirmacaoRecusada) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.motivos == [
        "Estoque insuficiente para CE285A: 2 em estoque, 8 no pedido.",
        "O desconto não pode passar do subtotal.",
    ]


def test_rascunho_vazio_e_sem_cliente_recebe_os_dois_motivos(vendedor):
    ped = montar_rascunho(vendedor)
    with pytest.raises(ConfirmacaoRecusada) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.motivos == [
        "Escolha o cliente antes de confirmar.",
        "Adicione pelo menos um produto.",
    ]


def test_produto_inativo_e_recusado_antes_de_atualizar_preco(vendedor):
    prod = com_estoque(criar_produto(preco="179.90"), 10)
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(prod, 1)])
    Produto.objects.filter(pk=prod.pk).update(ativo=False, preco=Decimal("189.90"))
    with pytest.raises(ConfirmacaoRecusada):
        confirmar_pedido(ped.pk, vendedor)
    assert ped.itens.get().preco_unitario == Decimal("179.90")


def test_estoque_de_milhar_aparece_formatado(vendedor):
    prod = com_estoque(criar_produto(), 1500)
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(prod, 1200)])
    Produto.objects.filter(pk=prod.pk).update(estoque=1100)
    with pytest.raises(ConfirmacaoRecusada) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.motivos == [
        "Estoque insuficiente para CE285A: 1.100 em estoque, 1.200 no pedido."
    ]


def test_pedido_ja_confirmado_nao_e_confirmado_de_novo(vendedor):
    prod = com_estoque(criar_produto(), 5)
    ped = montar_pedido_confirmado(vendedor, itens=[(prod, 2)])
    assert (ped.numero, ped.cliente.nome) == (1, "Papelaria Central Ltda")
    with pytest.raises(RegraDeNegocio, match="Este pedido não é mais um rascunho"):
        confirmar_pedido(ped.pk, vendedor)
    prod.refresh_from_db()
    assert prod.estoque == 3 and ContadorPedido.objects.get().ultimo_numero == 1


def test_vendedor_nao_confirma_rascunho_de_outro(vendedor, administrador):
    prod = com_estoque(criar_produto(), 5)
    outro = criar_usuario(email="outro@helptoner.com.br")
    ped = montar_rascunho(outro, cliente=criar_cliente(), itens=[(prod, 1)])
    with pytest.raises(PermissionDenied):
        confirmar_pedido(ped.pk, vendedor)
    ped = confirmar_pedido(ped.pk, administrador)
    assert (ped.criado_por, ped.confirmado_por) == (outro, administrador)
