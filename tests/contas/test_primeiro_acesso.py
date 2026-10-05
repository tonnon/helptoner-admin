from allauth.mfa.models import Authenticator

from apps.contas.middleware import etapa_do_primeiro_acesso
from apps.contas.models import Usuario
from tests.apoio import SENHA_TESTE, ativar_2fa, criar_usuario, totp_agora


def entrar_pelo_formulario(client, usuario):
    """Login de verdade (sem 2FA ativo, só a senha): o allauth registra a autenticação recente."""
    r = client.post("/contas/login/", {"login": usuario.email, "password": SENHA_TESTE})
    assert r.status_code == 302
    return r


def test_primeiro_acesso_obrigatorio_e_completo(client, db):
    # Deve trocar a senha e não tem 2FA.
    u = criar_usuario(pronto=False, email="nova@helptoner.com.br")
    entrar_pelo_formulario(client, u)  # sem 2FA: entra só com a senha
    for url in ["/", "/minha-conta/"]:
        assert client.get(url)["Location"] == "/primeiro-acesso/senha/"
    htmx = client.get("/", headers={"HX-Request": "true"})
    assert htmx["HX-Redirect"] == "/primeiro-acesso/senha/"
    mesma = {"new_password1": SENHA_TESTE, "new_password2": SENHA_TESTE}
    r = client.post("/primeiro-acesso/senha/", mesma)
    assert "A nova senha precisa ser diferente da senha temporária." in r.content.decode()
    nova = "toner-azul-de-março"
    client.post("/primeiro-acesso/senha/", {"new_password1": nova, "new_password2": nova})
    assert client.get("/")["Location"] == "/contas/2fa/totp/activate/"
    r = client.get("/contas/2fa/totp/activate/")
    segredo = r.context["form"].secret
    assert "<svg" in r.content.decode() and segredo in r.content.decode().replace(" ", "")
    r = client.post("/contas/2fa/totp/activate/", {"code": totp_agora(segredo)})
    assert r["Location"] == "/contas/2fa/recovery-codes/"
    assert client.get("/")["Location"] == "/contas/2fa/recovery-codes/"
    r = client.get("/contas/2fa/recovery-codes/")
    assert "Guardei os códigos, continuar" in r.content.decode()
    assert client.post("/primeiro-acesso/concluir/")["Location"] == "/"
    assert client.get("/").status_code == 200
    u.refresh_from_db()
    assert not u.deve_trocar_senha and u.codigos_recuperacao_entregues
    assert u.check_password(nova)


def test_sair_e_permitido_no_primeiro_acesso(client, db):
    client.force_login(criar_usuario(pronto=False))
    assert client.post("/contas/logout/").status_code == 302
    assert client.get("/")["Location"].startswith("/contas/login/")


def test_totp_apagado_por_fora_volta_para_a_etapa_2(client, db):
    u = criar_usuario()
    Authenticator.objects.filter(user=u).delete()
    client.force_login(u)  # dispara user_logged_in
    assert client.get("/")["Location"] == "/contas/2fa/totp/activate/"


def test_concluir_sem_totp_nao_conclui(client, db):
    u = criar_usuario(pronto=False)
    Usuario.objects.filter(pk=u.pk).update(deve_trocar_senha=False)
    client.force_login(u)
    client.post("/primeiro-acesso/concluir/")
    u.refresh_from_db()
    assert not u.codigos_recuperacao_entregues


def test_textos_da_etapa_1(client, db):
    client.force_login(criar_usuario(pronto=False))
    html = client.get("/primeiro-acesso/senha/").content.decode()
    assert "Primeiro acesso" in html and "1 · Nova senha" in html
    assert ">Nova senha</label>" in html and ">Confirme a nova senha</label>" in html
    assert ">Salvar e continuar</button>" in html
    assert 'action="/contas/logout/"' in html  # dá para sair no meio do caminho


def test_tela_do_autenticador(client, db):
    u = criar_usuario(pronto=False)
    Usuario.objects.filter(pk=u.pk).update(deve_trocar_senha=False)
    entrar_pelo_formulario(client, u)
    r = client.get("/contas/2fa/totp/activate/")
    html = r.content.decode()
    assert "1 · Nova senha ✓" in html and "2 · Autenticador" in html
    assert "Não consegue ler o QR? Digite esta chave no aplicativo" in html
    segredo = r.context["form"].secret
    em_grupos = " ".join(segredo[i : i + 4] for i in range(0, len(segredo), 4))
    assert f"data-segredo>{em_grupos}<" in html
    assert ">Código de 6 dígitos</label>" in html and ">Ativar e continuar</button>" in html
    assert "data:" not in html  # QR code em SVG na própria página (a CSP não libera data:)


def test_codigo_errado_nao_ativa_o_autenticador(client, db):
    u = criar_usuario(pronto=False)
    Usuario.objects.filter(pk=u.pk).update(deve_trocar_senha=False)
    entrar_pelo_formulario(client, u)
    client.get("/contas/2fa/totp/activate/")
    r = client.post("/contas/2fa/totp/activate/", {"code": "000000"})
    assert r.status_code == 200 and "campo-invalido" in r.content.decode()
    assert not Authenticator.objects.filter(user=u).exists()


def test_cada_etapa_so_libera_as_proprias_rotas(client, db):
    u = criar_usuario(pronto=False)
    client.force_login(u)
    # Etapa 1: nem o autenticador nem os códigos; a confirmação de senha do allauth, sim.
    for url in ["/contas/2fa/totp/activate/", "/contas/2fa/recovery-codes/"]:
        assert client.get(url)["Location"] == "/primeiro-acesso/senha/"
    assert client.get("/contas/reauthenticate/").status_code == 200
    # Etapa 3 (já com TOTP): nem a troca de senha sem a senha atual, nem outras telas.
    Usuario.objects.filter(pk=u.pk).update(deve_trocar_senha=False)
    ativar_2fa(u)
    for url in ["/primeiro-acesso/senha/", "/minha-conta/", "/contas/password/change/"]:
        assert client.get(url)["Location"] == "/contas/2fa/recovery-codes/"
    # O download passa; quem pede a senha de novo é o allauth (o force_login não conta como
    # login recente).
    r = client.get("/contas/2fa/recovery-codes/download/")
    assert r["Location"].startswith("/contas/reauthenticate/")
    assert client.get("/contas/2fa/reauthenticate/").status_code == 200


def test_troca_sem_senha_atual_nao_serve_para_quem_ja_trocou(client_vendedor, vendedor):
    nova = "toner-azul-de-março"
    r = client_vendedor.post(
        "/primeiro-acesso/senha/", {"new_password1": nova, "new_password2": nova}
    )
    assert r["Location"] == "/"
    vendedor.refresh_from_db()
    assert vendedor.check_password(SENHA_TESTE)


def test_quem_ja_concluiu_nao_gasta_consulta_com_o_primeiro_acesso(
    vendedor, django_assert_num_queries
):
    usuario = Usuario.objects.get(pk=vendedor.pk)
    with django_assert_num_queries(0):
        assert etapa_do_primeiro_acesso(usuario) is None
