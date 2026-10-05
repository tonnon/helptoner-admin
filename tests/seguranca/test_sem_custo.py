from types import SimpleNamespace

import pytest

from tests.apoio import com_estoque, criar_produto

# (url, pedaço HTMX?) das páginas em que o Vendedor nunca vê custo, lucro nem margem.
# As URLs podem ter {produto}, {pedido} e {rascunho}; as próximas tarefas acrescentam as suas.
PAGINAS = [
    ("/produtos/", True),
    ("/produtos/{produto}/", False),
    ("/estoque/", True),
]


@pytest.fixture
def cenario_custo(db):
    produto = criar_produto()
    com_estoque(produto, 5, "87.6543")  # movimento real: o custo também está no histórico
    return SimpleNamespace(produto=produto)


@pytest.mark.parametrize(("url", "htmx"), PAGINAS)
def test_vendedor_nunca_ve_custo(client_vendedor, cenario_custo, url, htmx):
    url = url.format(**{nome: obj.pk for nome, obj in vars(cenario_custo).items()})
    html = client_vendedor.get(url, headers={"HX-Request": "true"} if htmx else {}).content.decode()
    for proibido in ["87,65", "87,6543", "Custo", "custo médio", "Lucro", "Margem"]:
        assert proibido not in html, (url, proibido)


def test_administrador_ve_o_custo(client_admin, cenario_custo):
    html = client_admin.get("/produtos/", headers={"HX-Request": "true"}).content.decode()
    assert "R$ 87,65" in html
