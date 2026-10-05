from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.datas import hoje
from apps.pedidos.models import ContadorPedido
from tests.apoio import com_estoque, criar_produto, montar_pedido_confirmado


def test_registrar_entrada_pela_tela(client_admin):
    p = com_estoque(criar_produto(), 10, "60.00")
    r = client_admin.post(
        "/estoque/entrada/",
        {
            "codigo": "ce285a",
            "quantidade": "20",
            "custo_unitario": "80,00",
            "observacao": "NF 8812",
        },
    )
    assert r["Location"] == "/estoque/"
    p.refresh_from_db()
    assert p.estoque == 30


def test_regra_violada_aparece_no_formulario(client_admin):
    criar_produto()
    r = client_admin.post(
        "/estoque/ajuste/",
        {
            "codigo": "CE285A",
            "sentido": "mais",
            "quantidade": "1",
            "motivo": "contagem",
            "confirmar": "1",
        },
    )
    assert "Este produto ainda não tem custo" in r.content.decode()


def test_ajuste_pede_confirmacao(client_admin):
    p = com_estoque(criar_produto(), 5, "60.00")
    dados = {"codigo": "CE285A", "sentido": "menos", "quantidade": "1", "motivo": "avaria"}
    r = client_admin.post("/estoque/ajuste/", dados)
    assert "Confirme o ajuste" in r.content.decode() and p.movimentos.count() == 1
    client_admin.post("/estoque/ajuste/", dados | {"confirmar": "1"})
    assert p.movimentos.count() == 2


def test_historico_filtra_por_produto_e_periodo(client_vendedor):
    com_estoque(criar_produto("CE285A"), 5)
    com_estoque(criar_produto("TN-1060", descricao="Toner Brother TN-1060", marca="Brother"), 5)
    dia, ontem = hoje(), hoje() - timedelta(days=1)

    def get(q):
        return client_vendedor.get(
            f"/estoque/?{q}", headers={"HX-Request": "true"}
        ).content.decode()

    html = get(f"produto=CE285A&inicio={dia}&fim={dia}")
    assert "CE285A" in html and "TN-1060" not in html
    assert "Nenhum movimento no período." in get(f"inicio={ontem}&fim={ontem}")


def test_codigo_desconhecido(client_admin):
    r = client_admin.post(
        "/estoque/entrada/",
        {"codigo": "XXX", "quantidade": "1", "custo_unitario": "1,00", "observacao": "NF"},
    )
    assert "Produto não encontrado." in r.content.decode()


@pytest.mark.parametrize(
    "custo", ["NaN", "Infinity", "abc", "-5", "0", "1,23456", "12345678901,00"]
)
def test_custo_invalido_vira_erro_de_campo(client_admin, custo):
    p = criar_produto()
    r = client_admin.post(
        "/estoque/inicial/",
        {"codigo": "CE285A", "quantidade": "1", "custo_unitario": custo},
    )
    assert r.status_code == 200 and 'id="id_custo_unitario_error"' in r.content.decode()
    assert p.movimentos.count() == 0


def test_estoque_inicial_pela_tela_e_so_sem_movimentos(client_admin):
    p = criar_produto()
    dados = {"codigo": "CE285A", "quantidade": "7", "custo_unitario": "10,5"}
    assert client_admin.post("/estoque/inicial/", dados)["Location"] == "/estoque/"
    p.refresh_from_db()
    assert p.estoque == 7
    r = client_admin.post("/estoque/inicial/", dados)
    assert "já tem movimentos" in r.content.decode()


def test_datalist_do_estoque_inicial_so_tem_produtos_sem_movimentos(client_admin):
    com_estoque(criar_produto("CE285A"), 1)
    criar_produto("TN-1060")
    html = client_admin.get("/estoque/inicial/").content.decode()
    assert 'value="TN-1060"' in html and 'value="CE285A"' not in html


def test_historico_mostra_detalhe_e_custo_so_ao_administrador(client_admin, client_vendedor):
    com_estoque(criar_produto(), 5, "60.00")
    client_admin.post(
        "/estoque/entrada/",
        {"codigo": "CE285A", "quantidade": "3", "custo_unitario": "70,00", "observacao": "NF 1"},
    )
    cab = {"HX-Request": "true"}
    html = client_admin.get("/estoque/", headers=cab).content.decode()
    assert "Entrada · NF 1" in html and "+3" in html and "Custo unit." in html
    html_vendedor = client_vendedor.get("/estoque/", headers=cab).content.decode()
    assert "R$ 70,00" in html and "R$ 60,00" in html
    assert "Custo unit." not in html_vendedor
    assert "70,00" not in html_vendedor and "60,00" not in html_vendedor
    assert "+ Entrada" not in client_vendedor.get("/estoque/").content.decode()
    assert "+ Entrada" in client_admin.get("/estoque/").content.decode()


def test_historico_mostra_o_numero_do_pedido_na_saida(client_vendedor, vendedor):
    prod = com_estoque(criar_produto(), 20)
    ContadorPedido.objects.update(ultimo_numero=1041)
    montar_pedido_confirmado(vendedor, itens=[(prod, 2)])
    cab = {"HX-Request": "true"}

    def consultas():
        with CaptureQueriesContext(connection) as feitas:
            html = client_vendedor.get("/estoque/", headers=cab).content.decode()
        return html, len(feitas)

    html, com_uma_saida = consultas()
    assert "Saída · pedido nº 1.042" in html and "−2" in html
    montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    montar_pedido_confirmado(vendedor, itens=[(prod, 3)])
    html, com_tres_saidas = consultas()
    assert "Saída · pedido nº 1.044" in html and com_tres_saidas == com_uma_saida
