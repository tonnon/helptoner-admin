import pytest
from allauth.mfa.models import Authenticator
from django.db import connection
from django.test import override_settings

from apps.contas.models import RegistroAcesso, Usuario
from tests.apoio import SENHA_TESTE, UA_CHROME_WINDOWS, codigo_totp, criar_usuario


def entrar_com_senha(client, email, senha=SENHA_TESTE, **kw):
    return client.post("/contas/login/", {"login": email, "password": senha}, **kw)


def codigo_de_recuperacao(usuario) -> str:
    codigos = Authenticator.objects.get(user=usuario, type=Authenticator.Type.RECOVERY_CODES)
    return codigos.wrap().get_unused_codes()[0]


def test_login_com_senha_e_codigo(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    r = entrar_com_senha(client, "CARLA@helptoner.com.br")
    assert r.status_code == 302 and r["Location"] == "/contas/2fa/authenticate/"
    r = client.post("/contas/2fa/authenticate/", {"code": codigo_totp(u)})
    assert r.status_code == 302 and r["Location"] == "/"
    assert client.get("/").status_code == 200
    assert RegistroAcesso.objects.filter(usuario=u, sucesso=True).count() == 1


def test_codigo_errado_nao_entra_e_fica_registrado(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    entrar_com_senha(client, u.email)
    client.post("/contas/2fa/authenticate/", {"code": "000000"})
    assert client.get("/").status_code == 302
    assert RegistroAcesso.objects.get(sucesso=False).motivo == "Código de verificação inválido"


def test_senha_errada_fica_registrada_com_ip_e_navegador(client, db):
    criar_usuario(email="carla@helptoner.com.br")
    entrar_com_senha(
        client,
        "carla@helptoner.com.br",
        "senha-errada-de-novo",
        headers={"User-Agent": UA_CHROME_WINDOWS},
    )
    reg = RegistroAcesso.objects.get()
    assert (reg.sucesso, reg.email_tentado, reg.motivo, reg.ip, reg.navegador) == (
        False,
        "carla@helptoner.com.br",
        "E-mail ou senha incorretos",
        "127.0.0.1",
        UA_CHROME_WINDOWS,
    )


def test_bloqueio_da_conta_depois_de_5_erros_usa_o_cache_do_banco(client, db):
    criar_usuario(email="carla@helptoner.com.br")
    for _ in range(5):
        entrar_com_senha(client, "carla@helptoner.com.br", "senha-errada-de-novo")
    r = entrar_com_senha(client, "carla@helptoner.com.br")  # senha certa, mas bloqueada
    assert "Muitas tentativas erradas" in r.content.decode() and r.status_code == 200
    with connection.cursor() as c:
        c.execute("select count(*) from cache_django")
        assert c.fetchone()[0] > 0


def test_tentativa_bloqueada_tambem_fica_registrada(client, db):
    criar_usuario(email="carla@helptoner.com.br")
    for _ in range(5):
        entrar_com_senha(client, "carla@helptoner.com.br", "senha-errada-de-novo")
    entrar_com_senha(client, "carla@helptoner.com.br")
    registros = RegistroAcesso.objects.order_by("pk").values_list("sucesso", "motivo")
    assert list(registros) == [(False, "E-mail ou senha incorretos")] * 5 + [
        (False, "Bloqueado por excesso de tentativas")
    ]


@override_settings(ALLOWED_HOSTS=["helptoner.com.br"])
def test_bloqueio_da_conta_nao_depende_do_host(client, db):
    # O Django aceita o mesmo host em maiúsculas ou com porta; a conta segue bloqueada.
    criar_usuario(email="carla@helptoner.com.br")
    for i in range(5):  # um IP por tentativa, para o bloqueio por IP não entrar na conta
        entrar_com_senha(
            client,
            "carla@helptoner.com.br",
            "senha-errada-de-novo",
            HTTP_HOST="helptoner.com.br",
            REMOTE_ADDR=f"10.0.0.{i}",
        )
    variantes = ["HELPTONER.com.br", "helptoner.com.br:443", "helptoner.com.br:8443"]
    for i, host in enumerate(variantes):
        r = entrar_com_senha(
            client, "carla@helptoner.com.br", HTTP_HOST=host, REMOTE_ADDR=f"10.0.1.{i}"
        )
        assert r.status_code == 200 and "Muitas tentativas erradas" in r.content.decode(), host
    assert not RegistroAcesso.objects.filter(sucesso=True).exists()


def test_bloqueio_por_ip_depois_de_10_erros(client, db):
    for i in range(10):
        entrar_com_senha(client, f"ninguem{i}@x.com", "senha-errada-de-novo")
    r = entrar_com_senha(client, "outro@x.com", "senha-errada-de-novo")
    assert "Muitas tentativas erradas" in r.content.decode()


@override_settings(ALLAUTH_TRUSTED_CLIENT_IP_HEADER="x-vercel-forwarded-for")
def test_ip_vem_so_do_cabecalho_confiavel(client, db):
    entrar_com_senha(
        client,
        "x@x.com",
        "senha-errada-de-novo",
        headers={"x-vercel-forwarded-for": "200.1.2.3", "x-forwarded-for": "6.6.6.6"},
    )
    assert RegistroAcesso.objects.get().ip == "200.1.2.3"


def test_login_sem_ip_conhecido_fica_registrado_sem_ip(client, vendedor):
    client.force_login(vendedor)  # requisição montada pelo Django, sem REMOTE_ADDR
    reg = RegistroAcesso.objects.get()
    assert (reg.sucesso, reg.usuario, reg.ip, reg.navegador) == (True, vendedor, None, "")


@pytest.mark.parametrize(
    "url",
    [
        "/contas/signup/",
        "/contas/password/reset/",
        "/contas/email/",
        "/contas/2fa/totp/deactivate/",
    ],
)
def test_rotas_do_allauth_desligadas(client, db, url):
    assert client.get(url).status_code == 404


def test_usuario_desativado_nao_entra(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    Usuario.objects.filter(pk=u.pk).update(is_active=False)
    entrar_com_senha(client, u.email)
    assert client.get("/").status_code == 302
    assert not RegistroAcesso.objects.filter(sucesso=True).exists()
    reg = RegistroAcesso.objects.get(sucesso=False)
    assert (reg.motivo, reg.usuario, reg.email_tentado) == ("Acesso desativado", u, u.email)


def test_usuario_desativado_com_senha_errada_fica_registrado_sem_revelar_na_tela(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    Usuario.objects.filter(pk=u.pk).update(is_active=False)
    r = entrar_com_senha(client, u.email, "senha-errada-de-novo")
    assert "E-mail ou senha incorretos." in r.content.decode()  # a mesma tela de qualquer erro
    reg = RegistroAcesso.objects.get()
    assert (reg.sucesso, reg.motivo, reg.usuario) == (False, "Acesso desativado", u)


def test_usuario_desativado_ve_o_aviso(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    Usuario.objects.filter(pk=u.pk).update(is_active=False)
    r = entrar_com_senha(client, u.email, follow=True)
    assert "Acesso desativado" in r.content.decode()


def test_codigo_de_recuperacao_entra_pelo_mesmo_campo(client, db):
    u = criar_usuario()
    entrar_com_senha(client, u.email)
    r = client.post("/contas/2fa/authenticate/", {"code": codigo_de_recuperacao(u)})
    assert r.status_code == 302 and r["Location"] == "/"


def test_depois_do_codigo_volta_para_a_pagina_pedida(client, db):
    html = client.get("/contas/login/?next=/pedidos/7/").content.decode()
    assert '<input type="hidden" name="next" value="/pedidos/7/">' in html
    u = criar_usuario()
    client.post("/contas/login/?next=/pedidos/7/", {"login": u.email, "password": SENHA_TESTE})
    r = client.post("/contas/2fa/authenticate/", {"code": codigo_totp(u)})
    assert r["Location"] == "/pedidos/7/"


def test_textos_das_telas_de_login_e_de_verificacao(client, db):
    html = client.get("/contas/login/").content.decode()
    assert ">E-mail</label>" in html and ">Senha</label>" in html and ">Entrar</button>" in html
    assert "/contas/signup/" not in html and "/contas/password/reset/" not in html
    u = criar_usuario()
    entrar_com_senha(client, u.email)
    html = client.get("/contas/2fa/authenticate/").content.decode()
    assert "Verificação em duas etapas" in html and ">Código de 6 dígitos</label>" in html
    assert ">Verificar</button>" in html
    assert "Perdeu o celular? Use um código de recuperação" in html


@override_settings(ACCOUNT_RATE_LIMITS={"login": "1/m/ip"})
def test_requisicoes_demais_no_login_mostram_a_pagina_429(client, db):
    entrar_com_senha(client, "x@x.com", "senha-errada-de-novo")
    r = entrar_com_senha(client, "x@x.com", "senha-errada-de-novo")
    assert r.status_code == 429 and "Muitas tentativas" in r.content.decode()


def test_erros_na_reautenticacao_nao_entram_no_registro_de_acessos(client_vendedor):
    # Quem já entrou e erra a senha ou o código ao confirmar uma ação não está fazendo login.
    r = client_vendedor.post("/contas/reauthenticate/", {"password": "senha-errada-de-novo"})
    assert r.status_code == 200 and r.context["form"].errors
    r = client_vendedor.post("/contas/2fa/reauthenticate/", {"code": "000000"})
    assert r.status_code == 200 and r.context["form"].errors
    assert not RegistroAcesso.objects.filter(sucesso=False).exists()
