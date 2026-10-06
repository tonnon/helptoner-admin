from datetime import UTC, datetime

import pytest

from apps.pedidos.models import ContadorPedido, Pedido
from tests.apoio import (
    com_estoque,
    criar_cliente,
    criar_produto,
    montar_pedido_confirmado,
    montar_rascunho,
)

pytestmark = pytest.mark.django_db

HTMX = {"HX-Request": "true"}


def _lista(client, query=""):
    return client.get(f"/pedidos/{query}", headers=HTMX).content.decode()


def test_busca_por_numero_com_ou_sem_ponto(client_vendedor, vendedor):
    ContadorPedido.objects.update(ultimo_numero=1041)
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    for busca in ["1.042", "1042", "nº 1042"]:
        assert f"/pedidos/{ped.pk}/" in _lista(client_vendedor, f"?busca={busca}"), busca
    assert f"/pedidos/{ped.pk}/" not in _lista(client_vendedor, "?busca=1043")


def test_busca_por_numero_enorme_nao_quebra(client_vendedor):
    assert "Nenhum pedido" in _lista(client_vendedor, "?busca=99999999999999999999")


def test_busca_por_cliente_sem_acento(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(
        vendedor,
        cliente=criar_cliente("João da Silva", tipo="PF", documento="12345678909"),
        itens=[(com_estoque(criar_produto(), 5), 1)],
    )
    assert f"/pedidos/{ped.pk}/" in _lista(client_vendedor, "?busca=joao")
    assert f"/pedidos/{ped.pk}/" not in _lista(client_vendedor, "?busca=maria")


def test_filtro_de_status(client_vendedor, vendedor):
    produto = com_estoque(criar_produto(), 5)
    confirmado = montar_pedido_confirmado(vendedor, itens=[(produto, 1)])
    rascunho = montar_rascunho(vendedor)
    html = _lista(client_vendedor, "?status=rascunho")
    assert f"/pedidos/{rascunho.pk}/" in html and f"/pedidos/{confirmado.pk}/" not in html
    html = _lista(client_vendedor, "?status=confirmado")
    assert f"/pedidos/{confirmado.pk}/" in html and f"/pedidos/{rascunho.pk}/" not in html
    assert f"/pedidos/{rascunho.pk}/" in _lista(client_vendedor, "?status=invalido")


def test_filtro_de_mes_no_fuso_de_brasilia(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    Pedido.objects.filter(pk=ped.pk).update(
        confirmado_em=datetime(2026, 11, 1, 1, 30, tzinfo=UTC)  # 31/10 22h30 em Brasília
    )

    def get(mes):
        return _lista(client_vendedor, f"?mes={mes}")

    assert f"/pedidos/{ped.pk}/" in get("2026-10")
    assert f"/pedidos/{ped.pk}/" not in get("2026-11")
    assert f"/pedidos/{ped.pk}/" in get("lixo")  # mês inválido é ignorado


def test_rascunho_usa_a_data_de_criacao_no_filtro_de_mes(client_vendedor, vendedor):
    rascunho = montar_rascunho(vendedor)
    Pedido.objects.filter(pk=rascunho.pk).update(criado_em=datetime(2026, 3, 15, 12, tzinfo=UTC))
    assert f"/pedidos/{rascunho.pk}/" in _lista(client_vendedor, "?mes=2026-03")
    assert f"/pedidos/{rascunho.pk}/" not in _lista(client_vendedor, "?mes=2026-04")


def test_ordem_do_mais_recente_para_o_mais_antigo(client_vendedor, vendedor):
    produto = com_estoque(criar_produto(), 5)
    antigo = montar_pedido_confirmado(vendedor, itens=[(produto, 1)])
    novo = montar_pedido_confirmado(vendedor, itens=[(produto, 1)])
    Pedido.objects.filter(pk=antigo.pk).update(confirmado_em=datetime(2026, 1, 5, tzinfo=UTC))
    html = _lista(client_vendedor)
    assert html.index(f"/pedidos/{novo.pk}/") < html.index(f"/pedidos/{antigo.pk}/")


def test_vendedor_ve_todos_os_pedidos_com_quem_emitiu(client_vendedor, administrador):
    montar_pedido_confirmado(administrador, itens=[(com_estoque(criar_produto(), 5), 1)])
    assert "Lucas" in _lista(client_vendedor)


def test_lista_vazia_e_paginacao(client_vendedor, vendedor):
    assert "Nenhum pedido ainda. Comece um novo pedido." in _lista(client_vendedor)
    for _ in range(21):
        montar_rascunho(vendedor)
    assert "1–20 de 21" in _lista(client_vendedor)
    assert "21–21 de 21" in _lista(client_vendedor, "?pagina=2")
    html = _lista(client_vendedor, "?busca=zzz")
    assert "Nenhum pedido encontrado." in html and "ainda" not in html


def test_pagina_completa_traz_os_filtros(client_vendedor):
    html = client_vendedor.get("/pedidos/").content.decode()
    assert "Nº do pedido ou cliente" in html and 'name="status"' in html and 'name="mes"' in html
