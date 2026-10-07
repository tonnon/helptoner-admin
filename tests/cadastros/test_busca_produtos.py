import pytest

from apps.cadastros.buscas import buscar_produtos
from tests.apoio import criar_produto


@pytest.mark.parametrize("texto", ["ce285", "CE285A", "hp 85a", "toner hp", "HP"])
def test_busca_de_produto(db, texto):
    p = criar_produto("CE285A")
    criar_produto("TN-1060", descricao="Toner Brother TN-1060", marca="Brother")
    assert list(buscar_produtos(texto)) == [p]


def test_busca_ignora_traco_no_codigo(db):
    p = criar_produto("TN-1060", descricao="Toner Brother TN-1060", marca="Brother")
    assert list(buscar_produtos("tn1060")) == [p]


def test_busca_ignora_acento_na_descricao(db):
    p = criar_produto("CIL-1", descricao="Cilindro Fotocondutor", marca="Samsung")
    assert list(buscar_produtos("fotocondutór")) == [p]


def test_inativos_so_quando_pedidos_e_ordem_por_codigo(db):
    b = criar_produto("B-1")
    a = criar_produto("A-1")
    inativo = criar_produto("C-1", ativo=False)
    assert list(buscar_produtos("")) == [a, b]
    assert list(buscar_produtos("", incluir_inativos=True)) == [a, b, inativo]
    assert list(buscar_produtos("", limite=1)) == [a]


def test_caractere_nulo_na_busca_nao_quebra(client_vendedor):  # Ruling R23
    p = criar_produto("CE285A")
    assert list(buscar_produtos("ce\x00285")) == [p]
    r = client_vendedor.get("/produtos/?q=%00", headers={"HX-Request": "true"})
    assert r.status_code == 200 and "CE285A" in r.content.decode()
