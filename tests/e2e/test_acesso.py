import pytest
from playwright.sync_api import expect

from tests.apoio import SENHA_TESTE, criar_usuario, totp_agora
from tests.e2e.conftest import entrar

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_login_com_2fa(pagina, live_server, administrador):
    entrar(pagina, live_server, administrador)
    pagina.get_by_role("button", name="Sair").click()
    expect(pagina.get_by_label("E-mail")).to_be_visible()


def test_primeiro_acesso_completo(pagina, live_server):
    u = criar_usuario(pronto=False, email="nova@helptoner.com.br", nome="Nova Pessoa")
    pagina.goto(live_server.url + "/")
    pagina.get_by_label("E-mail").fill(u.email)
    pagina.get_by_label("Senha").fill(SENHA_TESTE)
    pagina.get_by_role("button", name="Entrar").click()
    pagina.get_by_label("Nova senha", exact=True).fill("toner-azul-de-março")
    pagina.get_by_label("Confirme a nova senha").fill("toner-azul-de-março")
    pagina.get_by_role("button", name="Salvar e continuar").click()
    segredo = pagina.locator("[data-segredo]").inner_text().replace(" ", "")
    pagina.get_by_label("Código de 6 dígitos").fill(totp_agora(segredo))
    pagina.get_by_role("button", name="Ativar e continuar").click()
    pagina.get_by_role("button", name="Guardei os códigos, continuar").click()
    expect(pagina.get_by_text("Olá, Nova")).to_be_visible()
