from allauth.mfa.models import Authenticator

from apps.contas.models import ADMINISTRADOR, Usuario
from tests.apoio import criar_usuario

AVISO_SENHA = "Copie e repasse ao funcionário. Ela não será mostrada de novo."


def _lista(client) -> str:
    return client.get("/funcionarios/", headers={"HX-Request": "true"}).content.decode()


def test_novo_funcionario_mostra_a_senha_uma_vez_so(client_admin):
    r = client_admin.post(
        "/funcionarios/novo/",
        {"nome": "Ana Lima", "email": "ana@helptoner.com.br", "perfil": "Vendedor"},
    )
    html = r.content.decode()
    assert "Copie e repasse ao funcionário" in html and "no-store" in r["Cache-Control"]
    lista = client_admin.get("/funcionarios/", headers={"HX-Request": "true"}).content.decode()
    assert "Ana Lima" in lista and "Pendente" in lista
    # A senha mostrada é a que vale, e não aparece em nenhum outro lugar.
    senha = r.context["senha"]
    assert senha in html and AVISO_SENHA in html
    assert Usuario.objects.get(email="ana@helptoner.com.br").check_password(senha)
    assert senha not in lista


def test_formulario_de_novo_funcionario(client_admin):
    html = client_admin.get("/funcionarios/novo/").content.decode()
    assert ">Nome</label>" in html and ">E-mail</label>" in html and ">Perfil</label>" in html
    assert '<option value="Vendedor" selected>' in html
    assert "no-store" not in client_admin.get("/funcionarios/novo/").get("Cache-Control", "")


def test_novo_funcionario_com_email_repetido(client_admin, vendedor):
    r = client_admin.post(
        "/funcionarios/novo/",
        {"nome": "Outra Carla", "email": "CARLA@helptoner.com.br", "perfil": "Vendedor"},
    )
    html = r.content.decode()
    assert r.status_code == 200 and "Já existe um funcionário com este e-mail." in html
    assert 'id="id_email_error"' in html and AVISO_SENHA not in html
    assert Usuario.objects.count() == 2


def test_lista_abre_com_esqueleto_e_busca_os_dados_por_htmx(client_admin):
    html = client_admin.get("/funcionarios/").content.decode()
    assert 'id="resultados"' in html and 'hx-trigger="load"' in html
    assert 'hx-get="/funcionarios/"' in html and "lucas@helptoner.com.br" not in html
    assert 'href="/funcionarios/novo/"' in html and "Novo funcionário" in html
    assert 'class="item-menu ativo" aria-current="page"' in html


def test_lista_com_as_colunas_do_esboco(client_admin, vendedor):
    criar_usuario(email="jose@helptoner.com.br", nome="José Pendente", pronto=False)
    desativado = criar_usuario(email="ex@helptoner.com.br", nome="Ex Funcionário")
    Usuario.objects.filter(pk=desativado.pk).update(is_active=False)
    lista = _lista(client_admin)
    for coluna in ["Nome", "E-mail", "Perfil", "2FA", "Situação"]:
        assert f">{coluna}</th>" in lista
    assert "Lucas Tonnon" in lista and "carla@helptoner.com.br" in lista
    assert "Administrador" in lista and "Vendedor" in lista
    assert "Ativo" in lista and "Pendente" in lista and "Desativado" in lista
    assert f'href="/funcionarios/{vendedor.pk}/"' in lista
    assert "<html" not in lista  # só o pedaço #resultados
    # Os ativos vêm primeiro, em ordem de nome.
    assert lista.index("Carla Souza") < lista.index("Lucas Tonnon") < lista.index("Ex Funcion")


def test_lista_nao_consulta_os_perfis_um_a_um(client_admin, django_assert_max_num_queries):
    for i in range(5):
        criar_usuario(email=f"v{i}@helptoner.com.br", nome=f"Vendedor {i}")
    with django_assert_max_num_queries(8):
        _lista(client_admin)


def test_editar_funcionario(client_admin, vendedor):
    html = client_admin.get(f"/funcionarios/{vendedor.pk}/").content.decode()
    assert 'value="Carla Souza"' in html and "carla@helptoner.com.br" in html
    assert '<option value="Vendedor" selected>' in html
    r = client_admin.post(
        f"/funcionarios/{vendedor.pk}/", {"nome": "Carla Souza Lima", "perfil": "Administrador"}
    )
    assert r["Location"] == "/funcionarios/"
    vendedor = Usuario.objects.get(pk=vendedor.pk)
    assert vendedor.nome == "Carla Souza Lima" and vendedor.perfil == ADMINISTRADOR
    assert vendedor.email == "carla@helptoner.com.br"  # o e-mail não muda por aqui


def test_proprio_perfil_fica_travado(client_admin, administrador):
    html = client_admin.get(f"/funcionarios/{administrador.pk}/").content.decode()
    select = html.split('<select name="perfil"')[1].split(">")[0]
    assert "disabled" in select
    assert "Você não pode mudar o seu próprio perfil." in html
    # Mesmo que o navegador envie outro perfil, o campo travado é ignorado.
    r = client_admin.post(
        f"/funcionarios/{administrador.pk}/", {"nome": "Lucas T.", "perfil": "Vendedor"}
    )
    assert r["Location"] == "/funcionarios/"
    u = Usuario.objects.get(pk=administrador.pk)
    assert u.eh_administrador and u.nome == "Lucas T."


def test_funcionario_inexistente(client_admin):
    assert client_admin.get("/funcionarios/999999/").status_code == 404
    assert client_admin.post("/funcionarios/999999/desativar/").status_code == 404


def test_acoes_so_por_post(client_admin, vendedor):
    for acao in ["redefinir-senha", "zerar-2fa", "desativar"]:
        assert client_admin.get(f"/funcionarios/{vendedor.pk}/{acao}/").status_code == 405


def test_acoes_pedem_confirmacao(client_admin, vendedor):
    html = client_admin.get(f"/funcionarios/{vendedor.pk}/").content.decode()
    for id_, acao in [
        ("redefinir-senha", "redefinir-senha"),
        ("zerar-2fa", "zerar-2fa"),
        ("desativar", "desativar"),
    ]:
        assert f'<dialog id="{id_}"' in html and f'data-abrir-dialogo="{id_}"' in html
        assert f'action="/funcionarios/{vendedor.pk}/{acao}/"' in html
    assert "btn-perigo" in html


def test_proprio_administrador_nao_tem_o_botao_de_desativar(client_admin, administrador):
    html = client_admin.get(f"/funcionarios/{administrador.pk}/").content.decode()
    assert 'data-abrir-dialogo="desativar"' not in html
    assert 'data-abrir-dialogo="redefinir-senha"' in html


def test_redefinir_senha_pela_tela(client_admin, vendedor):
    r = client_admin.post(f"/funcionarios/{vendedor.pk}/redefinir-senha/")
    html = r.content.decode()
    assert r.status_code == 200 and "no-store" in r["Cache-Control"] and AVISO_SENHA in html
    assert "Carla Souza" in html
    vendedor.refresh_from_db()
    assert vendedor.check_password(r.context["senha"]) and vendedor.deve_trocar_senha


def test_zerar_2fa_pela_tela(client_admin, vendedor):
    r = client_admin.post(f"/funcionarios/{vendedor.pk}/zerar-2fa/", follow=True)
    assert r.redirect_chain[-1][0] == f"/funcionarios/{vendedor.pk}/"
    assert "Verificação em duas etapas zerada." in r.content.decode()
    assert not Authenticator.objects.filter(user=vendedor).exists()


def test_desativar_pela_tela(client_admin, vendedor):
    r = client_admin.post(f"/funcionarios/{vendedor.pk}/desativar/", follow=True)
    assert r.redirect_chain[-1][0] == "/funcionarios/"
    assert "Funcionário desativado." in r.content.decode()
    assert not Usuario.objects.get(pk=vendedor.pk).is_active
    assert "Desativado" in _lista(client_admin)
    html = client_admin.get(f"/funcionarios/{vendedor.pk}/").content.decode()
    assert "data-abrir-dialogo" not in html  # nada a fazer com quem já foi desativado


def test_desativar_a_si_mesmo_pela_tela(client_admin, administrador):
    r = client_admin.post(f"/funcionarios/{administrador.pk}/desativar/", follow=True)
    assert r.redirect_chain[-1][0] == f"/funcionarios/{administrador.pk}/"
    assert "Você não pode desativar a si mesmo." in r.content.decode()
    assert Usuario.objects.get(pk=administrador.pk).is_active
