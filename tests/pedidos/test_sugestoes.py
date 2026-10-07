import pytest

from apps.pedidos.services import criar_rascunho
from tests.apoio import com_estoque, criar_cliente, criar_produto, montar_rascunho

pytestmark = pytest.mark.django_db

HTMX = {"HX-Request": "true"}


@pytest.fixture
def rascunho(vendedor):
    return criar_rascunho(vendedor)


def _clientes(client, rascunho, q):
    url = f"/pedidos/{rascunho.pk}/sugestoes/clientes/?q={q}"
    return client.get(url, headers=HTMX).content.decode()


def _produtos(client, rascunho, q):
    url = f"/pedidos/{rascunho.pk}/sugestoes/produtos/?q={q}"
    return client.get(url, headers=HTMX).content.decode()


def test_sugestoes_de_cliente_com_realce_e_sem_inativos(client_vendedor, rascunho):
    criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    criar_cliente("Joana Inativa", tipo="PF", ativo=False)
    html = client_vendedor.get(
        f"/pedidos/{rascunho.pk}/sugestoes/clientes/?q=joao"
    ).content.decode()
    assert "<mark>João</mark> da Silva" in html and "Joana" not in html


def test_sugestoes_escapam_html(client_vendedor, rascunho):
    criar_cliente("<b>Bar</b> & Cia")
    html = client_vendedor.get(f"/pedidos/{rascunho.pk}/sugestoes/clientes/?q=bar").content.decode()
    assert "&lt;b&gt;" in html and "<b>Bar" not in html


def test_sugestoes_de_produto_marcam_indisponiveis(client_vendedor, vendedor):
    criar_produto("CF217A", descricao="Toner HP 17A Preto")
    cheio = com_estoque(criar_produto("CE285A"), 3)
    ped = montar_rascunho(vendedor, itens=[(cheio, 3)])
    html = client_vendedor.get(f"/pedidos/{ped.pk}/sugestoes/produtos/?q=toner").content.decode()
    assert (
        "Sem estoque" in html
        and "Todo no pedido" in html
        and html.count('aria-disabled="true"') == 2
    )


def test_nada_encontrado(client_vendedor, rascunho):
    assert (
        "Nada encontrado para “zzz”."
        in client_vendedor.get(f"/pedidos/{rascunho.pk}/sugestoes/produtos/?q=zzz").content.decode()
    )


def test_opcao_de_cliente_e_um_botao_que_escolhe_o_cliente(client_vendedor, rascunho):
    cli = criar_cliente("Papelaria Central Ltda", documento="11222333000181", cidade="Campinas")
    html = _clientes(client_vendedor, rascunho, "papel")
    assert 'role="option"' in html and 'aria-selected="false"' in html
    assert f'hx-post="/pedidos/{rascunho.pk}/cliente/"' in html
    assert f'"cliente_id": "{cli.pk}"' in html
    assert "11.222.333/0001-81" in html and "Campinas" in html


def test_opcao_de_produto_leva_os_dados_da_linha_de_informacao(client_vendedor, vendedor):
    prod = com_estoque(criar_produto(preco="189.90"), 12)
    ped = montar_rascunho(vendedor, itens=[(prod, 3)])
    html = _produtos(client_vendedor, ped, "ce285")
    for trecho in [
        f'data-produto-id="{prod.pk}"',
        'data-texto="CE285A · Toner HP 85A Preto"',
        'data-preco="R$ 189,90"',
        'data-estoque="12"',
        'data-no-pedido="3"',
        "9 disponíveis",
        "<mark>CE285</mark>A",
    ]:
        assert trecho in html, trecho
    assert "aria-disabled" not in html and "hx-post" not in html


@pytest.mark.parametrize(
    ("estoque", "selo"),
    [
        (1, '<span class="tag-estoque baixo">1 disponível</span>'),
        (3, '<span class="tag-estoque baixo">3 disponíveis</span>'),
        (4, '<span class="tag-estoque">4 disponíveis</span>'),
    ],
)
def test_pouco_estoque_tem_selo_ambar(client_vendedor, rascunho, estoque, selo):
    com_estoque(criar_produto(), estoque)
    assert selo in _produtos(client_vendedor, rascunho, "ce285")


def test_no_maximo_seis_sugestoes(client_vendedor, rascunho):
    for n in range(7):
        criar_cliente(f"Papelaria {n}")
    assert _clientes(client_vendedor, rascunho, "papelaria").count('role="option"') == 6


def test_busca_vazia_nao_devolve_nada(client_vendedor, rascunho):
    criar_cliente("Papelaria Central Ltda")
    com_estoque(criar_produto(), 5)
    assert _clientes(client_vendedor, rascunho, "").strip() == ""
    assert _produtos(client_vendedor, rascunho, "%20%20").strip() == ""


def test_sugestoes_de_pedido_inexistente(client_vendedor):
    assert client_vendedor.get("/pedidos/999999/sugestoes/clientes/?q=a").status_code == 404
