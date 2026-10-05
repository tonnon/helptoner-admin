from django.conf import settings

from apps.contas.models import ADMINISTRADOR, Usuario
from tests.apoio import SENHA_TESTE, criar_usuario


def _superusuario(**extra):
    su = criar_usuario(ADMINISTRADOR, email="su@helptoner.com.br", **extra)
    Usuario.objects.filter(pk=su.pk).update(is_staff=True, is_superuser=True)
    return su


def test_painel_fica_num_endereco_nao_padrao(client_admin):
    assert settings.ADMIN_URL == "manutencao/"
    assert client_admin.get("/admin/").status_code == 404


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


def test_painel_respeita_o_primeiro_acesso(client, db):
    client.force_login(_superusuario(pronto=False))
    assert client.get("/manutencao/")["Location"] == "/primeiro-acesso/senha/"


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
