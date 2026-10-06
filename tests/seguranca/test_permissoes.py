import pytest

# (método, url) de cada rota que só o Administrador pode usar; o Vendedor recebe 403.
# Cada tarefa que criar uma rota só do administrador acrescenta aqui.
ROTAS_SO_ADMIN: list[tuple[str, str]] = []

ROTAS_SO_ADMIN += [
    ("get", "/funcionarios/"),
    ("get", "/funcionarios/novo/"),
    ("post", "/funcionarios/novo/"),
    ("get", "/funcionarios/1/"),
    ("post", "/funcionarios/1/"),
    ("post", "/funcionarios/1/redefinir-senha/"),
    ("post", "/funcionarios/1/zerar-2fa/"),
    ("post", "/funcionarios/1/desativar/"),
]

ROTAS_SO_ADMIN += [
    ("get", "/produtos/novo/"),
    ("post", "/produtos/novo/"),
    ("post", "/produtos/1/"),
    ("post", "/produtos/1/inativar/"),
    ("post", "/produtos/1/reativar/"),
]

ROTAS_SO_ADMIN += [
    ("get", "/estoque/entrada/"),
    ("post", "/estoque/entrada/"),
    ("get", "/estoque/inicial/"),
    ("post", "/estoque/inicial/"),
    ("get", "/estoque/ajuste/"),
    ("post", "/estoque/ajuste/"),
]

ROTAS_SO_ADMIN += [("post", "/pedidos/1/cancelar/")]


@pytest.mark.parametrize(("metodo", "url"), ROTAS_SO_ADMIN)
def test_vendedor_recebe_403(client_vendedor, metodo, url):
    r = getattr(client_vendedor, metodo.lower())(url)
    assert r.status_code == 403
