"""Alinhamento das telas: cabeçalho de tabela sobre os valores e cartões lado a lado."""

import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pytest

from apps.core.datas import hoje
from apps.relatorios.consultas import montar_aba
from tests.apoio import (
    F,
    com_estoque,
    criar_cliente,
    criar_produto,
    montar_pedido_confirmado,
)

RAIZ = Path(__file__).resolve().parents[2]
HX = {"HX-Request": "true"}


class _Tabelas(HTMLParser):
    """Lê cada <table>: a classe `num` de cada <th> e a da primeira linha de <td>."""

    def __init__(self):
        super().__init__()
        self.tabelas = []
        self._linha = None

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if tag == "table":
            self.tabelas.append({"th": [], "td": None})
        elif tag == "tr":
            self._linha = []
        elif tag in ("th", "td") and self._linha is not None:
            self._linha.append((tag, "num" in classes))

    def handle_endtag(self, tag):
        if tag == "tr" and self._linha:
            tabela = self.tabelas[-1]
            if self._linha[0][0] == "th":
                tabela["th"] = [num for _, num in self._linha]
            elif tabela["td"] is None:
                tabela["td"] = [num for _, num in self._linha]
            self._linha = None


def _tabelas(html: str):
    leitor = _Tabelas()
    leitor.feed(html)
    return [t for t in leitor.tabelas if t["th"] and t["td"]]


def _conferir(html: str):
    tabelas = _tabelas(html)
    assert tabelas, "nenhuma tabela com cabeçalho e linhas"
    for t in tabelas:
        # A coluna de ação (Repetir pedido) tem cabeçalho só para leitor de tela.
        n = len(t["th"])
        assert len(t["td"]) == n
        assert t["th"] == t["td"], f"cabeçalho e valores desalinhados: {t}"


@pytest.fixture
def dados(administrador):
    produto = com_estoque(criar_produto(), 10, "60.00", administrador)
    cliente = criar_cliente()
    montar_pedido_confirmado(administrador, cliente=cliente, itens=[(produto, 1)])
    return produto


@pytest.mark.parametrize(
    "url", ["/pedidos/", "/clientes/", "/produtos/", "/estoque/", "/funcionarios/", "/historico/"]
)
def test_cabecalho_acompanha_o_alinhamento_dos_valores(client_admin, dados, url):
    _conferir(client_admin.get(url, headers=HX).content.decode())


def test_cabecalho_do_detalhe_do_pedido(client_admin, dados):
    from apps.pedidos.models import Pedido

    pedido = Pedido.objects.get()
    _conferir(client_admin.get(f"/pedidos/{pedido.pk}/").content.decode())


@pytest.mark.parametrize("aba", ["vendas", "clientes", "produtos", "funcionarios", "estoque"])
def test_cabecalho_das_tabelas_dos_relatorios(client_admin, dados, aba):
    r = client_admin.get(f"/relatorios/{aba}/?atalho=ano", headers=HX)
    html = r.content.decode()
    if "<table" in html:
        _conferir(html)


def test_tabela_dos_relatorios_alinha_cabecalho_de_numero_e_data(administrador, dados):
    from django.template.loader import render_to_string

    tabela = montar_aba("clientes", F(date(2020, 1, 1), hoje()), hoje()).tabelas[0]
    _conferir(render_to_string("componentes/tabela.html", {"tabela": tabela}))


def test_produto_mostra_estoque_e_custo_junto_dos_rotulos(client_admin, dados):
    html = client_admin.get(f"/produtos/{dados.pk}/").content.decode()
    assert '<dt class="rotulo">Estoque</dt><dd class="font-semibold tabular-nums">' in html
    assert '<dt class="rotulo">Custo médio</dt><dd class="font-semibold tabular-nums">' in html
    assert '<dd class="num">' not in html


def test_cartoes_na_grade_nao_ganham_margem_de_irmao():
    css = (RAIZ / "tailwind" / "app.css").read_text(encoding="utf-8")
    assert ":is(.grid, .flex) > .cartao + .cartao" in css


def test_inicio_poe_os_dois_cartoes_na_grade(client_admin):
    html = client_admin.get("/", headers=HX).content.decode()
    assert 'grid gap-4 sm:grid-cols-2">\n  <div class="cartao">' in html


def test_observacoes_do_cliente_tem_espaco_de_cima(client_vendedor):
    html = client_vendedor.get("/clientes/novo/").content.decode()
    assert re.search(
        r'<div class="mt-3\.5">\s*<div class="grupo-campo">\s*<label[^>]*for="id_observacoes"', html
    )
