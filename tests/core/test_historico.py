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
    assert "Produto CE285A" in client_admin.get("/historico/", headers=HTMX).content.decode()


def test_mudanca_de_superusuario_sem_motivo_aparece(vendedor):
    vendedor.is_superuser = True
    vendedor.save()
    assert _hoje("funcionario")[0].descricao == (
        "Funcionário Carla Souza: superusuário (painel de manutenção) não → sim"
    )


def test_reativado_e_juncao_de_mudancas(administrador):
    c = criar_cliente(telefone="1", ativo=False)
    c.ativo = True
    c.save()
    assert _hoje("cliente")[0].descricao == "Cliente Papelaria Central Ltda reativado"
    c.ativo = False
    c.telefone = "2"
    c.save()
    assert _hoje("cliente")[0].descricao == (
        "Cliente Papelaria Central Ltda: inativado; telefone 1 → 2"
    )


def test_texto_longo_e_cortado(db):
    c = criar_cliente()
    c.observacoes = "x" * 100
    c.save()
    d = _hoje("cliente")[0].descricao
    assert d.endswith("— → " + "x" * 59 + "…")


def test_motivo_perde_a_palavra_funcionario(administrador, vendedor):
    from apps.contas.services import desativar_funcionario

    desativar_funcionario(vendedor, por=administrador)
    assert _hoje("funcionario")[0].descricao == "Funcionário Carla Souza: desativado"


def test_login_com_sucesso(client, db):
    from tests.apoio import SENHA_TESTE

    criar_usuario(email="carla@helptoner.com.br")
    client.post("/contas/login/", {"login": "carla@helptoner.com.br", "password": SENHA_TESTE})
    d = [e.descricao for e in _hoje("login")]
    assert not any(x.startswith("Login recusado") for x in d)


def test_nome_hostil_e_escapado(client_admin):
    criar_cliente("<script>alert(1)</script>")
    html = client_admin.get("/historico/", headers=HTMX).content.decode()
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


def test_periodo_vazio(client_admin):
    html = client_admin.get("/historico/?inicio=2020-01-01&fim=2020-01-02", headers=HTMX)
    assert "Nada registrado no período." in html.content.decode()


def test_data_fora_do_limite_usa_o_padrao(client_admin):
    r = client_admin.get("/historico/?fim=9999-12-31&inicio=0001-01-01", headers=HTMX)
    assert r.status_code == 200


def test_fronteira_do_dia_em_brasilia(db):
    from datetime import UTC, datetime

    dia = hoje()
    p1 = criar_produto("AAA1")
    p2 = criar_produto("BBB2")
    base = datetime(dia.year, dia.month, dia.day, tzinfo=UTC)
    from datetime import timedelta

    # 23:30 em Brasília de `dia` = 02:30 UTC do dia seguinte; 00:10 BRT do dia seguinte = 03:10 UTC.
    p1.history.update(history_date=base + timedelta(days=1, hours=2, minutes=30))
    p2.history.update(history_date=base + timedelta(days=1, hours=3, minutes=10))
    no_dia = [e.descricao for e in eventos(inicio=dia, fim=dia)]
    no_seguinte = [
        e.descricao for e in eventos(inicio=dia + timedelta(days=1), fim=dia + timedelta(days=1))
    ]
    assert no_dia == ["Produto AAA1 cadastrado"]
    assert no_seguinte == ["Produto BBB2 cadastrado"]


def test_paginacao_mantem_filtros(client_admin):
    for i in range(52):
        criar_produto(f"P{i:03d}")
    url = f"/historico/?tipo=produto&inicio={hoje()}&fim={hoje()}"
    html = client_admin.get(url, headers=HTMX).content.decode()
    assert "1–50 de 52" in html
    assert "pagina=2" in html and "tipo=produto" in html and f"inicio={hoje()}" in html
    pag2 = client_admin.get(url + "&pagina=2", headers=HTMX).content.decode()
    assert "51–52 de 52" in pag2


def test_dois_objetos_com_mudancas_intercaladas(administrador):
    a = criar_produto("AAA1", preco="1.00")
    b = criar_produto("BBB2", preco="10.00")
    for p, novo in ((a, "2.00"), (b, "20.00"), (a, "3.00"), (b, "30.00")):
        p.preco = novo
        p._history_user = administrador
        p.save()
    d = [e.descricao for e in _hoje("produto") if "cadastrado" not in e.descricao]
    assert d == [
        "Produto BBB2: preço R$ 20,00 → R$ 30,00",
        "Produto AAA1: preço R$ 2,00 → R$ 3,00",
        "Produto BBB2: preço R$ 10,00 → R$ 20,00",
        "Produto AAA1: preço R$ 1,00 → R$ 2,00",
    ]
