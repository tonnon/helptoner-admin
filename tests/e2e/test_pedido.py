import re
from decimal import Decimal
from pathlib import Path

import pytest
from playwright.sync_api import expect

from apps.pedidos.models import Pedido
from tests.apoio import com_estoque, criar_cliente, criar_produto
from tests.e2e.conftest import entrar

# serialized_rollback: o flush do fim de cada teste apaga o ContadorPedido e os grupos de perfil
# que vêm das migrações; sem isto, o pedido não teria número (Ruling R20).
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True, serialized_rollback=True)]


def _assentar_depois_de(pagina, acao) -> None:
    """Roda `acao` e espera o HTMX assentar a troca que ela provoca (evento htmx:afterSettle).

    O HTMX só liga os atributos hx-* do que acabou de chegar, e devolve o foco ao campo com
    autofocus, no fim da troca (uns 20 ms depois). Um teste é rápido o bastante para digitar
    nesse intervalo e perder o desconto. Um contador de htmx:afterSettle, lido antes da ação,
    dá uma espera exata, sem depender de classes do HTMX nem de pausas fixas.
    """
    antes = pagina.evaluate(
        """() => {
            if (window.__assentamentos === undefined) {
                window.__assentamentos = 0;
                document.addEventListener("htmx:afterSettle", () => window.__assentamentos++);
            }
            return window.__assentamentos;
        }"""
    )
    acao()
    pagina.wait_for_function("antes => window.__assentamentos > antes", arg=antes)


def _incluir_dois_toners(pagina) -> None:
    """Do menu até a lista de itens: pedido novo, cliente escolhido e 2 unidades do CE285A."""
    pagina.get_by_role("link", name="Pedidos", exact=True).click()  # o menu, não "Últimos pedidos"
    pagina.get_by_role("button", name="+ Novo pedido").click()
    # O clique só espera a página nova abrir, não os scripts. A busca depende do HTMX e do
    # sugestoes.js, que rodam antes do evento "load": digitar antes disso não dispara a busca.
    pagina.wait_for_url(re.compile(r"/pedidos/\d+/editar/"))
    pagina.get_by_placeholder("Buscar cliente por nome, CPF ou CNPJ").fill("papel")
    pagina.get_by_role("option", name=re.compile("Papelaria Central")).click()
    campo = pagina.get_by_placeholder("Buscar produto por código ou nome")
    campo.fill("ce285")
    # A busca espera 300 ms depois da última tecla: o Enter só escolhe com a lista na tela.
    expect(pagina.get_by_role("option", name=re.compile("CE285A"))).to_be_visible()
    campo.press("Enter")
    pagina.get_by_label("Quantidade").fill("2")
    # A resposta também redesenha o formulário do desconto: espera assentar antes de digitar nele.
    _assentar_depois_de(pagina, lambda: pagina.get_by_label("Quantidade").press("Enter"))
    expect(pagina.locator("#itens")).to_contain_text("Toner HP 85A Preto")


def test_pedido_do_comeco_ao_fim(pagina, live_server, administrador):
    criar_cliente("Papelaria Central Ltda", documento="11222333000181")
    prod = com_estoque(criar_produto(preco="189.90"), 12, por=administrador)
    entrar(pagina, live_server, administrador)
    _incluir_dois_toners(pagina)
    pagina.get_by_label("Desconto", exact=True).fill("10")
    pagina.get_by_label("Desconto", exact=True).blur()
    expect(pagina.locator("#resumo")).to_contain_text("R$ 341,82")
    pagina.get_by_role("button", name="Confirmar pedido").click()
    # O título da página também diz "Pedido nº 1 Confirmado": o aviso é procurado só na sua área.
    expect(pagina.locator("#avisos").get_by_text("Pedido nº 1 confirmado")).to_be_visible()
    with pagina.expect_download() as baixado:
        pagina.get_by_role("link", name="PDF", exact=True).click()
    assert Path(baixado.value.path()).read_bytes().startswith(b"%PDF-")
    pagina.wait_for_load_state("load")  # "Cancelar pedido" abre o diálogo pelo app.js
    pagina.get_by_role("button", name="Cancelar pedido").click()
    pagina.get_by_label("Motivo").fill("Cliente desistiu")
    pagina.get_by_role("dialog").get_by_role("button", name="Cancelar pedido").click()
    expect(pagina.get_by_text("Cancelado por Lucas")).to_be_visible()
    prod.refresh_from_db()
    assert prod.estoque == 12


def test_desconto_invalido_nao_confirma_e_depois_confirma_com_o_desconto_digitado(
    pagina, live_server, administrador
):
    criar_cliente("Papelaria Central Ltda", documento="11222333000181")
    prod = com_estoque(criar_produto(preco="189.90"), 12, por=administrador)
    entrar(pagina, live_server, administrador)
    _incluir_dois_toners(pagina)
    desconto = pagina.get_by_label("Desconto", exact=True)
    confirmar = pagina.get_by_role("button", name="Confirmar pedido")
    # Digita um desconto inválido e clica em Confirmar na hora, sem sair do campo antes: o pedido
    # continua rascunho, o campo mostra o erro e o estoque não mexe.
    desconto.fill("abc")
    _assentar_depois_de(pagina, confirmar.click)
    expect(pagina.locator("#erro-desconto")).to_contain_text("Informe um número")
    expect(desconto).to_have_attribute("aria-invalid", "true")
    expect(confirmar).to_be_enabled()
    rascunho = Pedido.objects.get()
    assert rascunho.status == Pedido.Status.RASCUNHO and rascunho.numero is None
    prod.refresh_from_db()
    assert prod.estoque == 12
    # Corrigido o valor, o mesmo clique imediato confirma com o desconto que está na tela.
    desconto.fill("10")
    confirmar.click()
    expect(pagina.locator("#avisos").get_by_text("Pedido nº 1 confirmado")).to_be_visible()
    pedido = Pedido.objects.get()
    assert pedido.status == Pedido.Status.CONFIRMADO and pedido.numero == 1
    assert pedido.desconto_valor == Decimal("37.98") and pedido.total == Decimal("341.82")
    prod.refresh_from_db()
    assert prod.estoque == 10
