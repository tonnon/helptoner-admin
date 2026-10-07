import pytest

from apps.cadastros.buscas import buscar_clientes, normalizar_busca
from tests.apoio import criar_cliente


@pytest.mark.parametrize("texto", ["joao", "JOÃO", "joão da", "123.456", "12345678909", "678909"])
def test_busca_acha_do_jeito_que_se_digita(db, texto):
    joao = criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    criar_cliente("Maria Souza", tipo="PF", documento="52998224725")
    assert list(buscar_clientes(texto)) == [joao]


@pytest.mark.parametrize("texto", ["%", "_", "'", "\\", "joao%"])
def test_caracteres_especiais_nao_quebram(db, texto):
    criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    assert list(buscar_clientes(texto)) == []


def test_inativo_fica_fora_da_busca(db):
    c = criar_cliente("João da Silva", tipo="PF", documento="12345678909", ativo=False)
    assert list(buscar_clientes("joao")) == []
    assert list(buscar_clientes("joao", incluir_inativos=True)) == [c]


def test_normalizar_busca():
    assert normalizar_busca("  joão   da  silva ") == "joão da silva"
    assert len(normalizar_busca("a" * 300)) == 100


def test_caractere_nulo_na_busca_nao_quebra(client_vendedor):  # Ruling R23
    joao = criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    assert normalizar_busca("jo\x00ao") == "joao"
    assert list(buscar_clientes("jo\x00ao")) == [joao]
    r = client_vendedor.get("/clientes/?q=%00", headers={"HX-Request": "true"})
    assert r.status_code == 200 and "João da Silva" in r.content.decode()


def test_limite(db):
    for i in range(3):
        criar_cliente(f"Cliente {i}")
    assert len(buscar_clientes("", limite=2)) == 2
