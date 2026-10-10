"""Telas dos relatórios (só o Administrador): abas, filtros, indicadores e gráficos.

Padrão P18: a primeira carga traz as abas, os filtros e o esqueleto; o HTMX busca o pedaço
"conteudo" na mesma URL. As consultas e as tabelas vêm de `montar_aba`; aqui só se formata o que
a tela mostra (blocos de indicadores e os dados dos gráficos).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.http import Http404
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_headers

from apps.contas.models import Usuario
from apps.core.datas import hoje
from apps.core.formatacao import brl, inteiro_br, percentual
from apps.core.htmx import eh_htmx
from apps.core.permissoes import requer_administrador

from .consultas import ABAS, Comparacao, montar_aba
from .periodos import (
    DIAS_SEM_COMPRAR,
    Agrupamento,
    Atalho,
    Filtros,
    ler_dias_sem_comprar,
    ler_filtros,
)

# Cores das séries (§7): azul da marca e laranja, aprovadas pelo validador de cores.
COR_FATURAMENTO = "#0200FF"
COR_LUCRO = "#eb6834"

NOMES_DO_AGRUPAMENTO = {
    Agrupamento.DIA: "dia",
    Agrupamento.SEMANA: "semana",
    Agrupamento.MES: "mês",
}
EXPORTACOES = (("excel", "⤓ Excel"), ("pdf", "⤓ PDF"))


@dataclass(frozen=True)
class Indicador:
    """Um bloco do Resumo: valor formatado e a variação contra o período anterior."""

    rotulo: str
    valor: str
    variacao: str  # "subiu 35%", "caiu 1", "sem variação" ou "sem vendas para comparar"
    sentido: str  # "sobe", "desce" ou "" (sem cor)
    principal: bool = False


def _sem_zero_decimal(texto: str) -> str:
    """'35,0%' → '35%'; '12,5%' fica igual."""
    return texto.replace(",0%", "%")


def _percentual_da_variacao(fracao: Decimal) -> str:
    return _sem_zero_decimal(percentual(fracao))


def _pontos_percentuais(diferenca: Decimal) -> str:
    return _sem_zero_decimal(percentual(diferenca)).replace("%", " p.p.")


def _indicador(c: Comparacao, campo: str, rotulo: str, valor: str, formatar, **extra):
    variacao = c.variacao(campo)
    if variacao is None:
        return Indicador(rotulo, valor, "sem vendas para comparar", "", **extra)
    texto = formatar(abs(variacao))
    if texto in ("0%", "0 p.p.", "0"):
        return Indicador(rotulo, valor, "sem variação", "", **extra)
    # O sentido vem dos próprios valores: com lucro anterior negativo, a fração troca de sinal.
    if getattr(c.atual, campo) > getattr(c.anterior, campo):
        return Indicador(rotulo, valor, f"subiu {texto}", "sobe", **extra)
    return Indicador(rotulo, valor, f"caiu {texto}", "desce", **extra)


def _blocos_de_indicadores(c: Comparacao) -> list[Indicador]:
    atual = c.atual
    return [
        _indicador(
            c,
            "faturamento",
            "Faturamento líquido",
            brl(atual.faturamento),
            _percentual_da_variacao,
            principal=True,
        ),
        _indicador(c, "lucro", "Lucro bruto", brl(atual.lucro), _percentual_da_variacao),
        _indicador(c, "margem", "Margem bruta", percentual(atual.margem), _pontos_percentuais),
        _indicador(c, "pedidos", "Pedidos confirmados", inteiro_br(atual.pedidos), inteiro_br),
        _indicador(
            c,
            "ticket_medio",
            "Valor médio por pedido",
            brl(atual.ticket_medio),
            _percentual_da_variacao,
        ),
    ]


def _plural(quantidade: int, singular: str, plural: str) -> str:
    return f"{inteiro_br(quantidade)} {singular if quantidade == 1 else plural}"


def _dados_do_grafico_de_linhas(serie: list[dict]) -> dict:
    """Faturamento líquido e lucro bruto no tempo: valores em texto decimal, textos prontos."""

    def linha(nome: str, cor: str, campo: str) -> dict:
        return {
            "nome": nome,
            "cor": cor,
            "valores": [str(ponto[campo]) for ponto in serie],
            "textos": [brl(ponto[campo]) for ponto in serie],
        }

    def detalhe(ponto: dict) -> str:
        pedidos = _plural(ponto["pedidos"], "pedido", "pedidos")
        if ponto["margem"] is None:
            return pedidos
        return f"Margem {percentual(ponto['margem'])} · {pedidos}"

    return {
        "rotulos": [ponto["rotulo"] for ponto in serie],
        "series": [
            linha("Faturamento líquido", COR_FATURAMENTO, "liquido"),
            linha("Lucro bruto", COR_LUCRO, "lucro"),
        ],
        "detalhes": [detalhe(ponto) for ponto in serie],
    }


def _dados_do_grafico_de_barras(produtos: list[dict]) -> dict:
    """Os produtos que mais faturaram, com lucro, margem e unidades para a caixa de valores."""
    return {
        "itens": [
            {
                "codigo": p["codigo"],
                "descricao": p["descricao"],
                "valor": str(p["faturamento"]),
                "texto": brl(p["faturamento"]),
                "detalhes": [
                    f"{brl(p['lucro'])} de lucro bruto · margem {percentual(p['margem'])}",
                    _plural(p["quantidade"], "unidade vendida", "unidades vendidas"),
                ],
            }
            for p in produtos
        ]
    }


@dataclass(frozen=True)
class Link:
    nome: str
    url: str
    ativa: bool = False


def _url_da_aba(aba: str) -> str:
    if aba == "resumo":
        return reverse("relatorios:resumo")
    return reverse("relatorios:aba", args=[aba])


def _abas(atual: str, query: str) -> list[Link]:
    """As abas mantêm os filtros (a mesma querystring que `ler_filtros` lê de volta)."""
    return [Link(nome, f"{_url_da_aba(aba)}?{query}", aba == atual) for aba, nome in ABAS.items()]


def _exportacoes(aba: str, query: str) -> list[Link]:
    """Os links "⤓ Excel" e "⤓ PDF" com os filtros; ficam de fora enquanto a rota não existe."""
    links = []
    for formato, nome in EXPORTACOES:
        try:
            url = reverse("relatorios:exportar", args=[aba, formato])
        except NoReverseMatch:
            return []
        links.append(Link(nome, f"{url}?{query}"))
    return links


def _opcoes_de_periodo(dia: date) -> list[tuple[str, str]]:
    return [
        (Atalho.TRES_MESES, "Últimos 3 meses"),
        (Atalho.ANO, f"{dia.year} até agora"),
        (Atalho.DOZE_MESES, "Últimos 12 meses"),
        (Atalho.DATAS, "Escolher datas…"),
    ]


def _funcionarios() -> list[tuple[int, str]]:
    return [
        (u.pk, u.nome if u.is_active else f"{u.nome} (inativo)")
        for u in Usuario.objects.order_by("nome", "pk").only("pk", "nome", "is_active")
    ]


@requer_administrador
@require_GET
@vary_on_headers("HX-Request")
def relatorio(request, aba: str = "resumo"):
    """Uma aba dos relatórios (padrão P18). Aba desconhecida dá 404."""
    if aba not in ABAS:
        raise Http404
    dia = hoje()
    f, erros = ler_filtros(request.GET, dia)
    dias = DIAS_SEM_COMPRAR
    query = f.como_querystring()
    query_exportar = query
    if aba == "clientes":  # só a aba Clientes tem o "sem comprar há mais de X dias" ajustável
        dias, erros_dias = ler_dias_sem_comprar(request.GET)
        erros += erros_dias
        query_exportar += f"&dias={dias}"
    contexto = {
        "aba": aba,
        "titulo": ABAS[aba],
        "f": f,
        "dias": dias,
        "abas": _abas(aba, query),
        "exportacoes": _exportacoes(aba, query_exportar),
    }
    if not eh_htmx(request):
        contexto |= {
            "periodos": _opcoes_de_periodo(dia),
            "agrupamentos": [
                (Agrupamento.DIA, "Dia"),
                (Agrupamento.SEMANA, "Semana"),
                (Agrupamento.MES, "Mês"),
            ],
            "funcionarios": _funcionarios(),
        }
        return render(request, "relatorios/pagina.html", contexto)

    rel = montar_aba(aba, f, dia, dias)
    contexto |= {"rel": rel, "erros": erros}
    if aba == "resumo":
        contexto |= _contexto_do_resumo(rel, f)
    return render(request, "relatorios/pagina.html#conteudo", contexto)


def _contexto_do_resumo(rel, f: Filtros) -> dict:
    return {
        "indicadores": _blocos_de_indicadores(rel.comparacao),
        "nome_do_agrupamento": NOMES_DO_AGRUPAMENTO[f.agrupamento],
        "dados_linha": _dados_do_grafico_de_linhas(rel.graficos["serie"]),
        "dados_barras": _dados_do_grafico_de_barras(rel.graficos["produtos"]),
    }
