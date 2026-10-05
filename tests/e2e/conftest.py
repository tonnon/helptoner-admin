import pytest
from playwright.sync_api import expect

from tests.apoio import SENHA_TESTE, codigo_totp

MARCAS_DE_CSP = ("Content Security Policy", "Refused to")


@pytest.fixture(autouse=True)
def permitir_django_no_laco_assincrono(monkeypatch):
    """O Playwright roda um laço assíncrono neste processo e o Django precisa poder consultar o
    banco de dentro dele. Vale só para os testes desta pasta."""
    monkeypatch.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture
def pagina(page, live_server):
    """A página do navegador. No fim do teste, falha se o console acusou violação de CSP."""
    mensagens: list[str] = []
    erros: list[str] = []
    page.on("console", lambda mensagem: mensagens.append(mensagem.text))
    page.on("pageerror", lambda erro: erros.append(str(erro)))
    yield page
    violacoes = [m for m in mensagens if any(marca in m for marca in MARCAS_DE_CSP)]
    assert not violacoes, f"Violação de CSP no console: {violacoes}"


def entrar(pagina, live_server, usuario) -> None:
    """Faz o login com senha e código do autenticador e espera ver o Início."""
    pagina.goto(live_server.url + "/")
    pagina.get_by_label("E-mail").fill(usuario.email)
    pagina.get_by_label("Senha").fill(SENHA_TESTE)
    pagina.get_by_role("button", name="Entrar").click()
    pagina.get_by_label("Código de 6 dígitos").fill(codigo_totp(usuario))
    pagina.get_by_role("button", name="Verificar").click()
    expect(pagina.get_by_text(f"Olá, {usuario.primeiro_nome}")).to_be_visible()
