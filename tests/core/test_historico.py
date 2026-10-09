from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cadastros.models import Cliente
from apps.contas.services import redefinir_senha
from apps.core.datas import hoje
from apps.core.historico import eventos
from tests.apoio import criar_cliente, criar_produto, criar_usuario

HTMX = {"HX-Request": "true"}


def _hoje(tipo=""):
    return eventos(tipo=tipo, inicio=hoje(), fim=hoje())


def test_mudanca_de_preco_com_antes_e_depois(client_admin):
    p = criar_produto(preco="179.90")
    client_admin.post(
        f"/produtos/{p.pk}/",
        {"codigo": "CE285A", "descricao": p.descricao, "marca": "HP", "preco": "189,90"},
    )
    e = _hoje()[0]
    assert (e.tipo, e.quem, e.descricao) == (
        "produto",
        "Lucas Tonnon",
        "Produto CE285A: preço R$ 179,90 → R$ 189,90",
    )


def test_cadastro_e_inativacao(client_vendedor):
    client_vendedor.post(
        "/clientes/novo/",
        {"tipo": "PJ", "nome": "Papelaria Central Ltda", "documento": "11.222.333/0001-81"},
    )
    client_vendedor.post(f"/clientes/{Cliente.objects.get().pk}/inativar/")
    assert [e.descricao for e in _hoje("cliente")] == [
        "Cliente Papelaria Central Ltda inativado",
        "Cliente Papelaria Central Ltda cadastrado",
    ]


def test_alteracao_de_texto_mostra_rotulo_e_valores(administrador):
    c = criar_cliente(telefone="1111")
    c.telefone = "2222"
    c._history_user = administrador
    c.save()
    assert _hoje("cliente")[0].descricao == "Cliente Papelaria Central Ltda: telefone 1111 → 2222"


def test_acoes_sobre_funcionarios(administrador, vendedor):
    redefinir_senha(vendedor, por=administrador)
    e = _hoje("funcionario")[0]
    assert (e.quem, e.descricao) == ("Lucas Tonnon", "Funcionário Carla Souza: senha redefinida")


def test_logins(client, db):
    criar_usuario(email="carla@helptoner.com.br")
    client.post(
        "/contas/login/", {"login": "carla@helptoner.com.br", "password": "senha-errada-de-novo"}
    )
    e = _hoje("login")[0]
    assert e.sucesso is False
    assert e.descricao == "Login recusado · carla@helptoner.com.br (E-mail ou senha incorretos)"


def test_registro_sem_diferenca_nao_aparece(vendedor):
    antes = len(_hoje("funcionario"))
    vendedor.last_login = timezone.now()
    vendedor.save(update_fields=["last_login"])
    assert len(_hoje("funcionario")) == antes


def test_tela_filtra_por_tipo(client_admin):
    criar_produto()
    html = client_admin.get("/historico/?tipo=cliente", headers=HTMX).content.decode()
    assert "Produto CE285A" not in html
    html = client_admin.get("/historico/?tipo=produto", headers=HTMX).content.decode()
    assert "Produto CE285A cadastrado" in html


def test_pagina_inteira_tem_filtros(client_admin):
    html = client_admin.get("/historico/").content.decode()
    assert "Funcionários" in html and 'name="tipo"' in html and 'id="resultados"' in html


def test_consultas_nao_crescem_com_os_registros(client_admin, administrador):
    def contar():
        with CaptureQueriesContext(connection) as q:
            assert client_admin.get("/historico/", headers=HTMX).status_code == 200
        return len(q)

    p = criar_produto()
    for i in range(3):
        p.preco = f"{i + 1}.00"
        p._history_user = administrador
        p.save()
    pequeno = contar()
    for i in range(10):
        p.preco = f"{i + 10}.00"
        p._history_user = administrador
        p.save()
        criar_cliente(f"Cliente {i}")
    assert contar() == pequeno
