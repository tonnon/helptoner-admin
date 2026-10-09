from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.pedidos.consultas import (
    NumerosDoMes,
    numeros_do_mes,
    rascunhos_abertos,
    ultimos_pedidos,
)
from apps.pedidos.models import Pedido
from apps.pedidos.services import cancelar_pedido, criar_rascunho
from tests.apoio import com_estoque, criar_produto, montar_pedido_confirmado, montar_rascunho

pytestmark = pytest.mark.django_db


def confirmar_em(pedido, quando):
    Pedido.objects.filter(pk=pedido.pk).update(confirmado_em=quando)


def test_numeros_do_mes_no_fuso_de_brasilia(administrador):
    prod = com_estoque(criar_produto(preco="100.00"), 10, por=administrador)
    a = montar_pedido_confirmado(administrador, itens=[(prod, 1)])
    b = montar_pedido_confirmado(administrador, itens=[(prod, 2)])
    confirmar_em(a, datetime(2026, 11, 1, 1, 30, tzinfo=UTC))  # 31/10 às 22h30 em Brasília
    confirmar_em(b, datetime(2026, 11, 1, 3, 30, tzinfo=UTC))  # 01/11 às 00h30 em Brasília
    n = numeros_do_mes(administrador, agora=datetime(2026, 11, 1, 2, 0, tzinfo=UTC))
    assert n == NumerosDoMes(1, Decimal("100.00"), "outubro")


def test_numeros_do_mes_sem_pedidos(administrador):
    n = numeros_do_mes(administrador, agora=datetime(2026, 3, 10, 12, 0, tzinfo=UTC))
    assert n == NumerosDoMes(0, Decimal("0"), "março")


def test_vendedor_ve_so_os_proprios_numeros_e_cancelado_nao_conta(administrador, vendedor):
    prod = com_estoque(criar_produto(preco="100.00"), 10, por=administrador)
    montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    montar_pedido_confirmado(administrador, itens=[(prod, 1)])
    cancelado = montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    cancelar_pedido(cancelado.pk, "x", administrador)
    assert numeros_do_mes(vendedor).pedidos == 1 and numeros_do_mes(administrador).pedidos == 2


def test_rascunhos_sao_os_da_propria_pessoa(vendedor, administrador):
    meu = criar_rascunho(vendedor)
    criar_rascunho(administrador)
    assert rascunhos_abertos(vendedor) == [meu]


def test_rascunhos_com_quantidade_de_itens_e_limite(vendedor, administrador):
    prod = com_estoque(criar_produto(), 10, por=administrador)
    com_itens = montar_rascunho(vendedor, itens=[(prod, 1)])
    for _ in range(5):
        criar_rascunho(vendedor)
    lista = rascunhos_abertos(vendedor, limite=3)
    assert len(lista) == 3 and com_itens not in lista
    assert all(r.quantidade_itens == 0 for r in lista)
    assert [r for r in rascunhos_abertos(vendedor, limite=10) if r == com_itens][
        0
    ].quantidade_itens == 1


def test_ultimos_pedidos_incluem_cancelados_e_nao_rascunhos(vendedor, administrador):
    prod = com_estoque(criar_produto(), 10, por=administrador)
    a = montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    b = montar_pedido_confirmado(administrador, itens=[(prod, 1)])
    cancelar_pedido(a.pk, "x", administrador)
    criar_rascunho(vendedor)
    assert ultimos_pedidos() == [b, a]
    assert ultimos_pedidos(limite=1) == [b]


def test_tela_do_inicio(client_vendedor, vendedor):
    assert "Olá, Carla" in client_vendedor.get("/").content.decode()
    criar_rascunho(vendedor)
    html = client_vendedor.get("/", headers={"HX-Request": "true"}).content.decode()
    assert "Pedidos em" in html and "Vendido em" in html and "Continuar" in html


def test_pagina_completa_tem_botao_e_painel_com_esqueleto(client_vendedor):
    html = client_vendedor.get("/").content.decode()
    assert "+ Novo pedido" in html and 'id="painel"' in html and "Carregando" in html
    assert "Rascunhos em aberto" not in html


def test_blocos_vazios_tem_orientacao(client_vendedor):
    html = client_vendedor.get("/", headers={"HX-Request": "true"}).content.decode()
    assert "Nenhum rascunho em aberto." in html and "Nenhum pedido ainda." in html


def test_ultimos_pedidos_na_tela(client_vendedor, vendedor, administrador):
    prod = com_estoque(criar_produto(preco="100.00"), 10, por=administrador)
    ped = montar_pedido_confirmado(administrador, itens=[(prod, 1)])
    html = client_vendedor.get("/", headers={"HX-Request": "true"}).content.decode()
    assert f"/pedidos/{ped.pk}/" in html and "R$ 100,00" in html and "Confirmado" in html
