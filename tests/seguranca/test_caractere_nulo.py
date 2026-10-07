"""Ruling R25: requisição com o caractere nulo, que o PostgreSQL não aceita em texto, recebe 400
antes de chegar às views (senão qualquer filtro ou campo que o levasse ao banco daria 500)."""

import pytest
from django.test import Client

from tests.apoio import com_estoque, criar_produto, montar_pedido_confirmado, montar_rascunho

HTMX = {"HX-Request": "true"}


@pytest.mark.parametrize(
    "url",
    [
        "/clientes/?q=%00",
        "/produtos/?q=%00",
        "/produtos/?marca=%00",
        "/estoque/?produto=%00",
        "/pedidos/?busca=%00",
        "/pedidos/{rascunho}/sugestoes/clientes/?q=%00",
        "/pedidos/{rascunho}/sugestoes/produtos/?q=ce%00285",
        "/clientes/?q%00=x",  # na chave também
    ],
)
def test_get_com_caractere_nulo_recebe_400(client_vendedor, vendedor, url):
    rascunho = montar_rascunho(vendedor)
    r = client_vendedor.get(url.format(rascunho=rascunho.pk), headers=HTMX)
    assert r.status_code == 400 and "Requisição inválida." in r.content.decode()


def test_post_com_caractere_nulo_recebe_400_e_nada_muda(client_admin, client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    r = client_admin.post(f"/pedidos/{ped.pk}/cancelar/", {"motivo": "Cliente\x00 desistiu"})
    assert r.status_code == 400
    ped.refresh_from_db()
    assert (ped.status, ped.motivo_cancelamento) == ("confirmado", "")
    rascunho = montar_rascunho(vendedor)
    url = f"/pedidos/{rascunho.pk}/observacoes/"
    r = client_vendedor.post(url, {"texto": "Entregar\x00 já"}, headers=HTMX)
    assert r.status_code == 400
    rascunho.refresh_from_db()
    assert rascunho.observacoes == ""


def test_requisicao_normal_passa(client_vendedor):
    assert client_vendedor.get("/clientes/?q=jo%C3%A3o%25", headers=HTMX).status_code == 200


def test_corpo_que_nao_e_formulario_passa(client_vendedor):
    r = client_vendedor.post("/clientes/", "a\x00b", content_type="application/json")
    assert r.status_code == 405  # chegou à view (a lista de clientes só aceita GET)


def test_recusa_de_quem_entrou_sem_consultar_o_banco(client_vendedor, django_assert_num_queries):
    # Depois do SessionMiddleware, a sessão seria gravada (SESSION_SAVE_EVERY_REQUEST).
    with django_assert_num_queries(0):
        r = client_vendedor.get("/clientes/?q=%00")
    assert r.status_code == 400


# Sem marcação de banco: se o middleware ou a página do 400 consultasse o banco (sessão, login,
# menu), o teste falharia.
def test_recusa_sem_tocar_no_banco():
    c = Client()
    r = c.get("/clientes/?q=%00")
    assert r.status_code == 400 and "Voltar ao início" in r.content.decode()
    assert c.post("/pedidos/1/observacoes/", {"texto": "a\x00"}).status_code == 400
    # Mesmos cabeçalhos de segurança das outras páginas.
    assert r["X-Frame-Options"] == "DENY" and r["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in r["Content-Security-Policy"]
