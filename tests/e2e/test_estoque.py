import pytest
from playwright.sync_api import expect

from tests.apoio import com_estoque, criar_produto
from tests.e2e.conftest import entrar

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_entrada_de_estoque(pagina, live_server, administrador):
    com_estoque(criar_produto(), 10, "60.00", por=administrador)
    entrar(pagina, live_server, administrador)
    pagina.get_by_role("link", name="Estoque").click()
    pagina.get_by_role("link", name="+ Entrada").click()
    pagina.get_by_label("Código do produto").fill("CE285A")
    pagina.get_by_label("Quantidade").fill("20")
    pagina.get_by_label("Custo unitário").fill("80,00")
    pagina.get_by_label("Observação").fill("NF 8812")
    pagina.get_by_role("button", name="Registrar").click()
    expect(pagina.get_by_text("Entrada · NF 8812")).to_be_visible()
    expect(pagina.get_by_text("+20")).to_be_visible()
