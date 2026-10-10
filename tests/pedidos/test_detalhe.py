import pytest

from apps.pedidos.models import Pedido
from tests.apoio import (
    com_estoque,
    criar_cliente,
    criar_produto,
    montar_pedido_confirmado,
    montar_rascunho,
)

pytestmark = pytest.mark.django_db


def test_detalhe_do_pedido(client_vendedor, vendedor):
    cli = criar_cliente("Papelaria Central Ltda", documento="11222333000181")
    ped = montar_pedido_confirmado(
        vendedor,
        cliente=cli,
        itens=[(com_estoque(criar_produto(preco="100.00"), 5), 2)],
        desconto=("percentual", "10"),
    )
    html = client_vendedor.get(f"/pedidos/{ped.pk}/").content.decode()
    for trecho in [
        "Pedido nº 1",
        "Confirmado",
        "11.222.333/0001-81",
        "Toner HP 85A Preto",
        "R$ 200,00",
        "Desconto (10%)",
        "− R$ 20,00",
        "R$ 180,00",
        "Emitido por Carla",
    ]:
        assert trecho in html
    assert "Cancelar pedido" not in html and "Lucro" not in html


def test_desconto_em_reais_sem_percentual(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(
        vendedor,
        itens=[(com_estoque(criar_produto(preco="100.00"), 5), 1)],
        desconto=("reais", "15"),
    )
    html = client_vendedor.get(f"/pedidos/{ped.pk}/").content.decode()
    assert "Desconto" in html and "Desconto (" not in html and "− R$ 15,00" in html


def test_detalhe_de_rascunho_e_pedido_inexistente(client_vendedor, vendedor):
    rascunho = montar_rascunho(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    html = client_vendedor.get(f"/pedidos/{rascunho.pk}/").content.decode()
    assert "Rascunho" in html and "Pedido nº" not in html
    assert client_vendedor.get("/pedidos/999999/").status_code == 404


def test_administrador_ve_lucro_e_cancela_com_motivo(client_admin, vendedor):
    ped = montar_pedido_confirmado(
        vendedor, itens=[(com_estoque(criar_produto(preco="100.00"), 5, "60.00"), 1)]
    )
    html = client_admin.get(f"/pedidos/{ped.pk}/").content.decode()
    assert "Lucro bruto R$ 40,00 · margem 40,0%" in html
    assert "Cancelar pedido" in html and "O estoque do produto volta." in html
    resposta = client_admin.post(f"/pedidos/{ped.pk}/cancelar/", {"motivo": ""}, follow=True)
    assert "Informe o motivo do cancelamento." in resposta.content.decode()
    resposta = client_admin.post(
        f"/pedidos/{ped.pk}/cancelar/", {"motivo": "Cliente desistiu"}, follow=True
    )
    assert "Pedido nº 1 cancelado. O estoque voltou." in resposta.content.decode()
    html = client_admin.get(f"/pedidos/{ped.pk}/").content.decode()
    assert "Cancelado por Lucas" in html and "Cliente desistiu" in html
    assert "Cancelar pedido" not in html


def test_cancelar_de_novo_mostra_o_erro_da_regra(client_admin, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    client_admin.post(f"/pedidos/{ped.pk}/cancelar/", {"motivo": "x"})
    resposta = client_admin.post(f"/pedidos/{ped.pk}/cancelar/", {"motivo": "y"}, follow=True)
    assert "Só pedidos confirmados podem ser cancelados." in resposta.content.decode()
    assert Pedido.objects.get(pk=ped.pk).motivo_cancelamento == "x"


def test_cancelar_so_aceita_post_e_pedido_existente(client_admin):
    assert client_admin.get("/pedidos/1/cancelar/").status_code == 405
    assert client_admin.post("/pedidos/999999/cancelar/", {"motivo": "x"}).status_code == 404


def test_vendedor_abre_rascunho_de_outro_usuario_so_para_ler(client_vendedor, administrador):
    rascunho = montar_rascunho(administrador, itens=[(com_estoque(criar_produto(), 5), 1)])
    resposta = client_vendedor.get(f"/pedidos/{rascunho.pk}/")
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Cancelar pedido" not in html and "/ Rascunho" in html


def test_aviso_do_cancelamento_no_plural(client_admin, vendedor):
    # Revisão final (M11): "O estoque dos 1 produtos volta." no pedido de um item só.
    a = com_estoque(criar_produto("CE285A"), 5)
    b = com_estoque(criar_produto("TN-1060", descricao="Toner Brother", marca="Brother"), 5)
    ped = montar_pedido_confirmado(vendedor, itens=[(a, 1), (b, 2)])
    assert (
        "O estoque dos 2 produtos volta."
        in client_admin.get(f"/pedidos/{ped.pk}/").content.decode()
    )
