import json
import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.relatorios.consultas import ABAS, Comparacao, Indicadores
from apps.relatorios.views import _blocos_de_indicadores

URL_SET = "?atalho=datas&inicio=2026-09-01&fim=2026-09-30"
URL_OUT = "?atalho=datas&inicio=2026-10-01&fim=2026-10-31"
HTMX = {"HX-Request": "true"}


def _pedaco(client, url: str) -> str:
    resposta = client.get(url, headers=HTMX)
    assert resposta.status_code == 200
    return resposta.content.decode()


def _json(html: str, id_: str) -> dict:
    achado = re.search(rf'<script id="{id_}" type="application/json">(.*?)</script>', html, re.S)
    assert achado, id_
    return json.loads(achado.group(1))


def _hoje(monkeypatch, dia: date) -> None:
    monkeypatch.setattr("apps.relatorios.views.hoje", lambda: dia)


def test_resumo_com_indicadores_e_comparacao(client_admin, cenario):
    html = client_admin.get("/relatorios/" + URL_SET, headers=HTMX).content.decode()
    for trecho in ["R$ 325,00", "R$ 125,00", "38,5%", "R$ 162,50", "vs 30 dias anteriores"]:
        assert trecho in html
    assert 'id="dados-grafico-linha" type="application/json"' in html
    assert "Faturamento líquido" in html and "<table" in html  # toda visualização tem a tabela


@pytest.mark.parametrize(
    "aba", ["vendas", "clientes", "produtos", "funcionarios", "estoque", "cancelamentos"]
)
def test_cada_aba_abre(client_admin, cenario, aba):
    r = client_admin.get(f"/relatorios/{aba}/{URL_SET}", headers=HTMX)
    assert r.status_code == 200 and ABAS[aba] in r.content.decode()


def test_filtro_invalido_mostra_aviso(client_admin):
    r = client_admin.get("/relatorios/?atalho=datas&inicio=2026-10-05&fim=2026-10-01", headers=HTMX)
    assert "A data inicial precisa ser antes da final." in r.content.decode()


def test_aba_desconhecida(client_admin):
    assert client_admin.get("/relatorios/nada/").status_code == 404


def test_primeira_carga_com_esqueleto_filtros_e_abas(client_admin, cenario):
    url = f"/relatorios/vendas/{URL_SET}&agrupamento=semana&funcionario={cenario.carla.pk}"
    html = client_admin.get(url).content.decode()
    assert "<h1" in html and "Vendas por período</h1>" in html
    assert 'class="osso' in html and "R$ 325,00" not in html  # os números chegam por HTMX
    assert 'id="relatorio"' in html and 'hx-trigger="load"' in html
    assert f'hx-get="{url.replace("&", "&amp;")}"' in html
    # Barra de filtros: GET com HTMX, conteúdo apagado no lugar enquanto carrega.
    assert 'method="get" action="/relatorios/vendas/"' in html
    assert 'hx-get="/relatorios/vendas/"' in html and 'hx-target="#relatorio"' in html
    assert 'hx-push-url="true"' in html and 'hx-indicator="#relatorio"' in html
    assert '<option value="datas" selected>Escolher datas…</option>' in html
    assert '<option value="semana" selected>Semana</option>' in html
    assert f'<option value="{cenario.carla.pk}" selected>Carla Souza</option>' in html
    assert 'name="inicio" value="2026-09-01"' in html and 'name="fim" value="2026-09-30"' in html
    assert 'name="dias"' not in html  # só na aba Clientes
    assert "js/graficos.js" in html
    assert 'href="/relatorios/" class="item-menu ativo" aria-current="page"' in html


def test_abas_mantem_os_filtros(client_admin, cenario):
    url = f"/relatorios/?atalho=3m&agrupamento=semana&funcionario={cenario.carla.pk}"
    query = f"atalho=3m&amp;agrupamento=semana&amp;funcionario={cenario.carla.pk}"
    pagina = client_admin.get(url).content.decode()
    pedaco = _pedaco(client_admin, url)
    for html in (pagina, pedaco):
        assert f'<a href="/relatorios/clientes/?{query}" class="aba">Clientes</a>' in html
        assert (
            f'<a href="/relatorios/?{query}" class="aba ativa" aria-current="page">Resumo</a>'
            in html
        )
    # Depois de trocar o filtro, as abas voltam junto com o conteúdo (com os filtros novos).
    assert 'id="abas-relatorio"' in pedaco and 'hx-swap-oob="innerHTML"' in pedaco


def test_links_de_exportacao_com_os_filtros(client_admin, monkeypatch):
    def reverse_com_exportar(nome, *args, **kwargs):  # a rota de exportação chega na Tarefa 27
        if nome == "relatorios:exportar":
            aba, formato = kwargs["args"]
            return f"/relatorios/{aba}/{formato}/"
        return reverse(nome, *args, **kwargs)

    monkeypatch.setattr("apps.relatorios.views.reverse", reverse_com_exportar)
    url = "/relatorios/vendas/?atalho=3m"
    for html in (client_admin.get(url).content.decode(), _pedaco(client_admin, url)):
        query = "atalho=3m&amp;agrupamento=mes"
        assert f'<a href="/relatorios/vendas/excel/?{query}" class="btn-sec">⤓ Excel</a>' in html
        assert f'<a href="/relatorios/vendas/pdf/?{query}" class="btn-sec">⤓ PDF</a>' in html


def test_variacao_dos_indicadores(client_admin, cenario):
    # 01 a 03/10 contra 28 a 30/09: R$ 135,00 contra R$ 100,00, 1 pedido contra 1.
    html = _pedaco(client_admin, "/relatorios/?atalho=datas&inicio=2026-10-01&fim=2026-10-03")
    assert html.count('class="delta sobe"><span aria-hidden="true">▲</span> subiu 35%') == 2
    assert "subiu 87,5%" in html and "subiu 15,6 p.p." in html  # lucro; margem em pontos
    assert '<p class="delta">sem variação' in html  # pedidos
    assert "vs 3 dias anteriores" in html

    # Outubro contra os 31 dias anteriores (setembro): tudo cai, menos a margem.
    html = _pedaco(client_admin, "/relatorios/" + URL_OUT)
    assert 'class="delta desce"><span aria-hidden="true">▼</span> caiu 58,5%' in html
    assert "caiu 40%" in html and "subiu 17,1 p.p." in html
    assert "caiu 1 " in html and "caiu 16,9%" in html  # pedidos em número; valor médio
    assert "vs 31 dias anteriores" in html

    # Setembro contra agosto, sem vendas: não há base para a variação em reais.
    html = _pedaco(client_admin, "/relatorios/" + URL_SET)
    assert html.count("sem vendas para comparar") == 4 and "subiu 2 " in html


def test_variacao_com_lucro_anterior_negativo():
    # De -R$ 100,00 para R$ 50,00 o lucro subiu, embora a fração (50 + 100) / -100 seja negativa.
    anterior = Indicadores(Decimal("100.00"), Decimal("-100.00"), Decimal("-1.0000"), 2, None)
    atual = Indicadores(Decimal("100.00"), Decimal("50.00"), Decimal("0.5000"), 1, None)
    blocos = _blocos_de_indicadores(Comparacao(atual, anterior, "vs 30 dias anteriores"))
    lucro, margem, pedidos = blocos[1], blocos[2], blocos[3]
    assert (lucro.variacao, lucro.sentido) == ("subiu 150%", "sobe")
    assert (margem.variacao, margem.sentido) == ("subiu 150 p.p.", "sobe")
    assert (pedidos.variacao, pedidos.sentido) == ("caiu 1", "desce")


def test_graficos_em_json_com_texto_decimal(client_admin, cenario):
    html = _pedaco(client_admin, "/relatorios/" + URL_SET)
    assert _json(html, "dados-grafico-linha") == {
        "rotulos": ["set/26"],
        "series": [
            {
                "nome": "Faturamento líquido",
                "cor": "#0200FF",
                "valores": ["325.00"],
                "textos": ["R$ 325,00"],
            },
            {
                "nome": "Lucro bruto",
                "cor": "#eb6834",
                "valores": ["125.00"],
                "textos": ["R$ 125,00"],
            },
        ],
        "detalhes": ["Margem 38,5% · 2 pedidos"],
    }
    assert _json(html, "dados-grafico-barras") == {
        "itens": [
            {
                "codigo": "CE285A",
                "descricao": "Toner HP 85A Preto",
                "valor": "280.00",
                "texto": "R$ 280,00",
                "detalhes": ["R$ 100,00 de lucro bruto · margem 35,7%", "3 unidades vendidas"],
            },
            {
                "codigo": "TN-1060",
                "descricao": "Toner Brother TN-1060",
                "valor": "45.00",
                "texto": "R$ 45,00",
                "detalhes": ["R$ 25,00 de lucro bruto · margem 55,6%", "1 unidade vendida"],
            },
        ]
    }
    # Cada gráfico tem a chave "Gráfico | Tabela" e a tabela pronta, escondida.
    assert html.count('data-vista="tabela" aria-pressed="false"') == 2
    assert html.count("<div data-vista-tabela hidden>") == 2
    assert "Faturamento líquido e lucro bruto por mês" in html


def test_periodo_sem_vendas_nao_desenha_barras(client_admin, cenario):
    html = _pedaco(client_admin, "/relatorios/?atalho=datas&inicio=2026-08-01&fim=2026-08-31")
    assert "dados-grafico-barras" not in html and "Nenhuma venda no período." in html
    assert _json(html, "dados-grafico-linha")["series"][0]["valores"] == ["0.00"]
    assert _json(html, "dados-grafico-linha")["detalhes"] == ["0 pedidos"]


def test_tabela_formata_cada_tipo(client_admin, cenario):
    html = _pedaco(
        client_admin, "/relatorios/produtos/?atalho=datas&inicio=2026-09-01&fim=2026-10-31"
    )
    assert '<table class="tabela-responsiva">' in html
    assert '<th scope="col" class="num">Participação</th>' in html
    assert '<td data-rotulo="Participação" class="num">60,9%</td>' in html
    assert '<td data-rotulo="Faturamento" class="num">R$ 280,00</td>' in html
    assert '<td data-rotulo="Quantidade" class="num">3</td>' in html
    assert '<td data-rotulo="Código">CE285A</td>' in html

    html = _pedaco(client_admin, "/relatorios/cancelamentos/" + URL_OUT)
    assert '<td data-rotulo="Data do cancelamento" class="num">03/10/2026</td>' in html
    assert '<td data-rotulo="Motivo">Cliente desistiu</td>' in html

    html = _pedaco(client_admin, "/relatorios/cancelamentos/" + URL_SET)
    assert "Nada para mostrar com estes filtros." in html


def test_clientes_sem_comprar_com_repetir_pedido(client_admin, cenario, monkeypatch):
    _hoje(monkeypatch, date(2026, 12, 1))  # Clínica: 62 dias; Papelaria: 60 (fica de fora)
    html = _pedaco(client_admin, "/relatorios/" + URL_SET)
    assert "Clientes sem comprar há mais de 60 dias" in html
    assert "Clínica Bem Viver" in html and "Papelaria Central Ltda" not in html
    assert html.count('action="/pedidos/') == 1
    assert f'<form method="post" action="/pedidos/{cenario.pedido2.pk}/repetir/">' in html
    assert "csrfmiddlewaretoken" in html and ">Repetir pedido</button>" in html


def test_aba_clientes_com_dias_ajustaveis(client_admin, cenario, monkeypatch):
    _hoje(monkeypatch, date(2026, 11, 10))  # Clínica: 41 dias; Papelaria: 39
    pagina = client_admin.get("/relatorios/clientes/?dias=40").content.decode()
    assert 'name="dias" value="40"' in pagina

    html = _pedaco(client_admin, "/relatorios/clientes/?dias=40")
    assert "Clientes sem comprar há mais de 40 dias" in html
    assert html.count('action="/pedidos/') == 1
    assert f'action="/pedidos/{cenario.pedido2.pk}/repetir/"' in html

    html = _pedaco(client_admin, "/relatorios/clientes/?dias=0")
    assert "Número de dias inválido." in html
    assert "Clientes sem comprar há mais de 60 dias" in html


def test_resposta_varia_com_o_htmx(client_admin):
    assert "HX-Request" in client_admin.get("/relatorios/")["Vary"]
