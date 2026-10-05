import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.contas.models import ADMINISTRADOR, VENDEDOR, Usuario
from config.settings.base import normalizar_admin_url
from tests.apoio import SENHA_TESTE, criar_usuario, totp_agora


def _superusuario(perfil=ADMINISTRADOR, **extra):
    su = criar_usuario(perfil, email="su@helptoner.com.br", **extra)
    Usuario.objects.filter(pk=su.pk).update(is_staff=True, is_superuser=True)
    return su


def test_painel_fica_num_endereco_nao_padrao(client_admin):
    assert settings.ADMIN_URL == "manutencao/"
    assert client_admin.get("/admin/").status_code == 404


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("manutencao/", "manutencao/"),
        ("segredo", "segredo/"),
        ("/segredo-123/", "segredo-123/"),
        (" painel/interno ", "painel/interno/"),
    ],
)
def test_endereco_do_painel_ganha_uma_barra_no_fim(valor, esperado):
    assert normalizar_admin_url(valor) == esperado


@pytest.mark.parametrize("valor", ["", " ", "/", "admin", "Admin/", "/ADMIN/"])
def test_endereco_do_painel_nao_pode_ser_vazio_nem_o_padrao(valor):
    with pytest.raises(ImproperlyConfigured, match="ADMIN_URL"):
        normalizar_admin_url(valor)


def test_painel_pede_login_do_sistema(client, db):
    assert client.get("/manutencao/")["Location"] == "/contas/login/?next=/manutencao/"


def test_login_proprio_do_painel_leva_ao_login_do_sistema(client, db):
    r = client.get("/manutencao/login/?next=/manutencao/")
    assert r.status_code == 302 and r["Location"].startswith("/contas/login/?next=")
    assert "manutencao" in r["Location"]


def test_administrador_comum_nao_entra_no_painel(client_admin):
    assert client_admin.get("/manutencao/", follow=True).status_code == 403


def test_superusuario_entra_no_painel(client, db):
    su = criar_usuario(ADMINISTRADOR, email="su@helptoner.com.br")
    Usuario.objects.filter(pk=su.pk).update(is_staff=True, is_superuser=True)
    client.force_login(su)
    assert client.get("/manutencao/").status_code == 200


def test_superusuario_no_perfil_vendedor_nao_entra_no_painel(client, db):
    client.force_login(_superusuario(VENDEDOR))
    assert client.get("/manutencao/", follow=True).status_code == 403


def test_painel_respeita_o_primeiro_acesso(client, db):
    client.force_login(_superusuario(pronto=False))
    assert client.get("/manutencao/")["Location"] == "/primeiro-acesso/senha/"


def test_administrador_comum_nao_toma_a_conta_do_superusuario(client, client_admin):
    # O caminho da revisão: zera o 2FA e redefine a senha do superusuário, entra com a senha
    # temporária e conclui o primeiro acesso com o próprio celular. Com a Ruling R15, a conta
    # perde o acesso ao painel no caminho.
    su = _superusuario()
    client_admin.post(f"/funcionarios/{su.pk}/zerar-2fa/")
    senha = client_admin.post(f"/funcionarios/{su.pk}/redefinir-senha/").context["senha"]
    assert client.post("/contas/login/", {"login": su.email, "password": senha}).status_code == 302
    nova = "toner-azul-de-março"
    client.post("/primeiro-acesso/senha/", {"new_password1": nova, "new_password2": nova})
    segredo = client.get("/contas/2fa/totp/activate/").context["form"].secret
    client.post("/contas/2fa/totp/activate/", {"code": totp_agora(segredo)})
    client.post("/primeiro-acesso/concluir/")
    assert client.get("/").status_code == 200  # primeiro acesso concluído
    assert client.get("/manutencao/", follow=True).status_code == 403


def test_formulario_de_login_do_django_nunca_e_usado(client, db):
    # Ele entra sem a verificação em duas etapas: nem quem tem só o "acesso ao painel de
    # manutenção" (is_staff) nem o superusuário podem enviar a senha (de outra pessoa) por ele.
    su = _superusuario()
    staff = criar_usuario(ADMINISTRADOR, email="staff@helptoner.com.br")
    Usuario.objects.filter(pk=staff.pk).update(is_staff=True)
    credenciais = {"username": su.email, "password": SENHA_TESTE}
    client.force_login(staff)
    assert client.get("/manutencao/login/").status_code == 403
    assert client.post("/manutencao/login/", credenciais).status_code == 403
    client.force_login(su)
    assert client.get("/manutencao/login/")["Location"] == "/manutencao/"
    assert client.post("/manutencao/login/", credenciais).status_code == 403


def test_registro_de_acessos_so_para_leitura(client, db):
    client.force_login(_superusuario())
    assert client.get("/manutencao/contas/registroacesso/").status_code == 200
    assert client.get("/manutencao/contas/registroacesso/add/").status_code == 403
