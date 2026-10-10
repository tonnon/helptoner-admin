"""Consultas dos relatórios: indicadores, série, produtos, clientes, estoque e cancelamentos."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Max,
    Q,
    QuerySet,
    Sum,
)
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek

from apps.cadastros.models import Produto
from apps.core.datas import FUSO, intervalo_de_datas
from apps.core.dinheiro import arredondar
from apps.estoque.models import MovimentoEstoque
from apps.pedidos.calculos import margem
from apps.pedidos.models import ItemPedido, Pedido
from apps.relatorios.periodos import (
    Agrupamento,
    Filtros,
    descricao_comparacao,
    periodo_anterior,
)
from apps.relatorios.tabelas import Coluna, Tabela

ZERO = Decimal("0.00")
_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _decimal(expressao) -> ExpressionWrapper:
    return ExpressionWrapper(expressao, output_field=DecimalField(max_digits=16, decimal_places=4))


_BRUTO = _decimal(F("quantidade") * F("preco_unitario"))
_RECEITA = _decimal(F("quantidade") * F("preco_unitario") - F("desconto_rateado"))
_CUSTO = _decimal(F("quantidade") * F("custo_unitario"))


def itens_confirmados(f: Filtros) -> QuerySet[ItemPedido]:
    """Itens de pedidos confirmados no intervalo de Brasília, com `receita` e `custo` anotados."""
    inicio, fim = intervalo_de_datas(f.inicio, f.fim)
    itens = ItemPedido.objects.filter(
        pedido__status=Pedido.Status.CONFIRMADO,
        pedido__confirmado_em__gte=inicio,
        pedido__confirmado_em__lt=fim,
    )
    if f.funcionario_id is not None:
        itens = itens.filter(pedido__criado_por=f.funcionario_id)
    return itens.annotate(receita=_RECEITA, custo=_CUSTO)


@dataclass(frozen=True)
class Indicadores:
    faturamento: Decimal
    lucro: Decimal
    margem: Decimal | None
    pedidos: int
    ticket_medio: Decimal | None


def indicadores(f: Filtros) -> Indicadores:
    total = itens_confirmados(f).aggregate(
        receita_total=Sum("receita"),
        custo_total=Sum("custo"),
        pedidos=Count("pedido", distinct=True),
    )
    receita = total["receita_total"] or ZERO
    custo = total["custo_total"] or ZERO
    pedidos = total["pedidos"]
    faturamento = arredondar(receita)
    lucro = arredondar(receita - custo)
    ticket = arredondar(receita / pedidos) if pedidos else None
    return Indicadores(faturamento, lucro, margem(lucro, faturamento), pedidos, ticket)


@dataclass(frozen=True)
class Comparacao:
    atual: Indicadores
    anterior: Indicadores
    descricao: str

    def variacao(self, campo: str) -> Decimal | int | None:
        atual, anterior = getattr(self.atual, campo), getattr(self.anterior, campo)
        if campo == "pedidos":
            return atual - anterior
        if atual is None or anterior is None:
            return None
        if campo == "margem":
            return atual - anterior
        if not anterior:
            return None
        return ((atual - anterior) / anterior).quantize(Decimal("0.0001"))


def comparar(f: Filtros) -> Comparacao:
    return Comparacao(indicadores(f), indicadores(periodo_anterior(f)), descricao_comparacao(f))


def _inicio_do_periodo(dia: date, agrupamento: Agrupamento) -> date:
    if agrupamento == Agrupamento.MES:
        return dia.replace(day=1)
    if agrupamento == Agrupamento.SEMANA:
        return dia - timedelta(days=dia.weekday())
    return dia


def _proximo(dia: date, agrupamento: Agrupamento) -> date:
    if agrupamento == Agrupamento.MES:
        return (dia.replace(day=28) + timedelta(days=4)).replace(day=1)
    return dia + timedelta(days=7 if agrupamento == Agrupamento.SEMANA else 1)


def _rotulo(dia: date, agrupamento: Agrupamento) -> str:
    if agrupamento == Agrupamento.MES:
        return f"{_MESES[dia.month - 1]}/{dia.year % 100:02d}"
    return f"{dia.day:02d}/{dia.month:02d}"


def serie(f: Filtros) -> list[dict]:
    """Uma linha por dia, semana (a partir da segunda) ou mês de Brasília, com os vazios zerados."""
    truncar = {
        Agrupamento.DIA: TruncDay,
        Agrupamento.SEMANA: TruncWeek,
        Agrupamento.MES: TruncMonth,
    }[f.agrupamento]
    grupos = (
        itens_confirmados(f)
        .annotate(periodo=truncar("pedido__confirmado_em", tzinfo=FUSO))
        .values("periodo")
        .annotate(
            pedidos=Count("pedido", distinct=True),
            bruto=Sum(_BRUTO),
            receita_total=Sum("receita"),
            custo_total=Sum("custo"),
        )
        .order_by("periodo")
    )
    por_periodo = {g["periodo"].astimezone(FUSO).date(): g for g in grupos}

    linhas = []
    dia = _inicio_do_periodo(f.inicio, f.agrupamento)
    while dia <= f.fim:
        g = por_periodo.get(dia)
        if g is None:
            valores = dict(
                pedidos=0, bruto=ZERO, descontos=ZERO, liquido=ZERO, lucro=ZERO,
                margem=None, ticket=None,
            )  # fmt: skip
        else:
            bruto, liquido = arredondar(g["bruto"]), arredondar(g["receita_total"])
            lucro = arredondar(g["receita_total"] - g["custo_total"])
            valores = dict(
                pedidos=g["pedidos"],
                bruto=bruto,
                descontos=bruto - liquido,
                liquido=liquido,
                lucro=lucro,
                margem=margem(lucro, liquido),
                ticket=arredondar(g["receita_total"] / g["pedidos"]),
            )
        linhas.append({"periodo": dia, "rotulo": _rotulo(dia, f.agrupamento), **valores})
        dia = _proximo(dia, f.agrupamento)
    return linhas


def top_produtos(f: Filtros, limite: int = 6) -> list[dict]:
    grupos = (
        itens_confirmados(f)
        .values("produto_id", "produto__codigo", "produto__descricao")
        .annotate(qtd=Sum("quantidade"), receita_total=Sum("receita"), custo_total=Sum("custo"))
        .order_by("-receita_total", "produto__codigo")[:limite]
    )
    resultado = []
    for g in grupos:
        faturamento = arredondar(g["receita_total"])
        lucro = arredondar(g["receita_total"] - g["custo_total"])
        resultado.append(
            {
                "codigo": g["produto__codigo"],
                "descricao": g["produto__descricao"],
                "quantidade": g["qtd"],
                "faturamento": faturamento,
                "lucro": lucro,
                "margem": margem(lucro, faturamento),
            }
        )
    return resultado


def clientes_sem_comprar(dias: int, hoje: date, funcionario_id: int | None = None) -> list[dict]:
    """Clientes cujo último pedido confirmado (data de Brasília) é de mais de `dias` dias atrás.

    Com `funcionario_id`, o "último pedido" é o último pedido confirmado emitido POR ELE (a
    carteira dele): um cliente que comprou depois com outro funcionário continua na lista.
    """
    pedidos = Pedido.objects.filter(status=Pedido.Status.CONFIRMADO, cliente__isnull=False)
    if funcionario_id is not None:
        pedidos = pedidos.filter(criado_por=funcionario_id)
    ultimos = (
        pedidos.select_related("cliente")
        .prefetch_related("itens")
        .order_by("cliente_id", "-confirmado_em", "-pk")
        .distinct("cliente_id")
    )
    resultado = []
    for pedido in ultimos:
        dia = pedido.confirmado_em.astimezone(FUSO).date()
        parados = (hoje - dia).days
        if parados > dias:
            itens = sorted(pedido.itens.all(), key=lambda item: item.pk)
            resultado.append(
                {
                    "cliente_id": pedido.cliente_id,
                    "nome": pedido.cliente.nome,
                    "ultimo_pedido": dia,
                    "ultimo_pedido_id": pedido.pk,
                    "dias": parados,
                    "produtos": [item.codigo for item in itens][:3],
                }
            )
    resultado.sort(key=lambda r: (-r["dias"], r["nome"]))
    return resultado


_CASAS_DA_FRACAO = Decimal("0.0001")


def _fracao(parte: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0.0000")
    return (parte / total).quantize(_CASAS_DA_FRACAO, rounding=ROUND_HALF_UP)


def _pedidos_confirmados(f: Filtros) -> QuerySet[Pedido]:
    inicio, fim = intervalo_de_datas(f.inicio, f.fim)
    pedidos = Pedido.objects.filter(
        status=Pedido.Status.CONFIRMADO, confirmado_em__gte=inicio, confirmado_em__lt=fim
    )
    if f.funcionario_id is not None:
        pedidos = pedidos.filter(criado_por=f.funcionario_id)
    return pedidos


def ranking_clientes(f: Filtros) -> list[dict]:
    """Clientes por valor comprado no período; `ultimo_pedido` vale para qualquer período."""
    grupos = list(
        itens_confirmados(f)
        .filter(pedido__cliente__isnull=False)
        .values("pedido__cliente_id", "pedido__cliente__nome")
        .annotate(
            pedidos=Count("pedido", distinct=True),
            receita_total=Sum("receita"),
            custo_total=Sum("custo"),
        )
    )
    ultimos_pedidos = Pedido.objects.filter(
        status=Pedido.Status.CONFIRMADO,
        cliente_id__in=[g["pedido__cliente_id"] for g in grupos],
    )
    if f.funcionario_id is not None:
        ultimos_pedidos = ultimos_pedidos.filter(criado_por=f.funcionario_id)
    ultimos = {
        u["cliente_id"]: u["ultimo"].astimezone(FUSO).date()
        for u in ultimos_pedidos.values("cliente_id").annotate(ultimo=Max("confirmado_em"))
    }
    resultado = [
        {
            "cliente_id": g["pedido__cliente_id"],
            "nome": g["pedido__cliente__nome"],
            "valor": arredondar(g["receita_total"]),
            "pedidos": g["pedidos"],
            "lucro": arredondar(g["receita_total"] - g["custo_total"]),
            "ultimo_pedido": ultimos[g["pedido__cliente_id"]],
        }
        for g in grupos
    ]
    resultado.sort(key=lambda r: (-r["valor"], r["nome"]))
    return resultado


def _linhas_de_vendas(f: Filtros, campos: dict[str, str]) -> list[dict]:
    """Agrupa os itens por `campos` ({nome na saída: caminho}) e calcula as métricas."""
    grupos = list(
        itens_confirmados(f)
        .values(*campos.values())
        .annotate(qtd=Sum("quantidade"), receita_total=Sum("receita"), custo_total=Sum("custo"))
    )
    total = sum((g["receita_total"] for g in grupos), Decimal("0"))
    linhas = []
    for g in grupos:
        faturamento = arredondar(g["receita_total"])
        lucro = arredondar(g["receita_total"] - g["custo_total"])
        linhas.append(
            {
                **{nome: g[caminho] for nome, caminho in campos.items()},
                "quantidade": g["qtd"],
                "faturamento": faturamento,
                "lucro": lucro,
                "margem": margem(lucro, faturamento),
                "participacao": _fracao(g["receita_total"], total),
            }
        )
    return linhas


def produtos(f: Filtros) -> list[dict]:
    linhas = _linhas_de_vendas(
        f,
        {"codigo": "produto__codigo", "descricao": "produto__descricao", "marca": "produto__marca"},
    )
    linhas.sort(key=lambda r: (-r["faturamento"], r["codigo"]))
    return linhas


def marcas(f: Filtros) -> list[dict]:
    linhas = _linhas_de_vendas(f, {"marca": "produto__marca"})
    linhas.sort(key=lambda r: (-r["faturamento"], r["marca"]))
    return linhas


def funcionarios(f: Filtros) -> list[dict]:
    """Por quem emitiu: pedidos, valor, lucro e desconto médio (Σ desconto ÷ Σ subtotal)."""
    grupos = (
        itens_confirmados(f)
        .values("pedido__criado_por_id", "pedido__criado_por__nome")
        .annotate(
            pedidos=Count("pedido", distinct=True),
            receita_total=Sum("receita"),
            custo_total=Sum("custo"),
        )
    )
    descontos = {
        d["criado_por_id"]: d
        for d in _pedidos_confirmados(f)
        .values("criado_por_id")
        .annotate(desconto=Sum("desconto_valor"), subtotal_total=Sum("subtotal"))
    }
    resultado = []
    for g in grupos:
        d = descontos[g["pedido__criado_por_id"]]
        resultado.append(
            {
                "usuario_id": g["pedido__criado_por_id"],
                "nome": g["pedido__criado_por__nome"],
                "pedidos": g["pedidos"],
                "valor": arredondar(g["receita_total"]),
                "lucro": arredondar(g["receita_total"] - g["custo_total"]),
                "desconto_medio": _fracao(d["desconto"], d["subtotal_total"]),
            }
        )
    resultado.sort(key=lambda r: (-r["valor"], r["nome"]))
    return resultado


def estoque(f: Filtros) -> dict:
    """Situação atual dos produtos ativos e os movimentos de estoque do período."""
    linhas = [
        {
            "codigo": p.codigo,
            "descricao": p.descricao,
            "estoque": p.estoque,
            "custo_medio": p.custo_medio,
            "valor_em_estoque": arredondar(p.estoque * p.custo_medio),
        }
        for p in Produto.objects.filter(ativo=True).order_by("codigo")
    ]
    inicio, fim = intervalo_de_datas(f.inicio, f.fim)
    movimentos = MovimentoEstoque.objects.filter(criado_em__gte=inicio, criado_em__lt=fim)
    if f.funcionario_id is not None:
        movimentos = movimentos.filter(usuario=f.funcionario_id)
    tipo = MovimentoEstoque.Tipo

    def soma(*tipos: str) -> Sum:
        return Sum("quantidade", filter=Q(tipo__in=tipos))

    somas = movimentos.aggregate(
        entradas=soma(tipo.INICIAL, tipo.ENTRADA),
        saidas=soma(tipo.SAIDA),
        devolucoes=soma(tipo.DEVOLUCAO),
        ajustes_mais=soma(tipo.AJUSTE_MAIS),
        ajustes_menos=soma(tipo.AJUSTE_MENOS),
    )
    return {
        "produtos": linhas,
        "zerados": [linha["codigo"] for linha in linhas if linha["estoque"] == 0],
        "movimentos": {nome: valor or 0 for nome, valor in somas.items()},
        "valor_total": sum((linha["valor_em_estoque"] for linha in linhas), ZERO),
    }


def cancelamentos(f: Filtros) -> list[dict]:
    """Pedidos cancelados no período (data do cancelamento, em Brasília)."""
    inicio, fim = intervalo_de_datas(f.inicio, f.fim)
    pedidos = Pedido.objects.filter(
        status=Pedido.Status.CANCELADO, cancelado_em__gte=inicio, cancelado_em__lt=fim
    )
    if f.funcionario_id is not None:
        pedidos = pedidos.filter(criado_por=f.funcionario_id)
    pedidos = pedidos.select_related("cliente", "cancelado_por", "criado_por").order_by(
        "-cancelado_em", "-pk"
    )
    return [
        {
            "pedido_id": p.pk,
            "numero": p.numero,
            "cliente": p.cliente.nome if p.cliente else "",
            "valor": p.total,
            "motivo": p.motivo_cancelamento,
            "cancelado_por": p.cancelado_por.nome if p.cancelado_por else "",
            "cancelado_em": p.cancelado_em,
            "emitido_por": p.criado_por.nome,
        }
        for p in pedidos
    ]


ABAS = {
    "resumo": "Resumo",
    "vendas": "Vendas por período",
    "clientes": "Clientes",
    "produtos": "Produtos e marcas",
    "funcionarios": "Funcionários",
    "estoque": "Estoque",
    "cancelamentos": "Cancelamentos",
}


@dataclass(frozen=True)
class Relatorio:
    aba: str
    titulo: str
    tabelas: list[Tabela]
    comparacao: Comparacao | None = None
    graficos: dict | None = None


def _tabela_sem_comprar(dias: int, hoje: date, f: Filtros, titulo: str) -> Tabela:
    clientes = clientes_sem_comprar(dias, hoje, f.funcionario_id)
    return Tabela(
        titulo,
        [
            Coluna("Cliente", "texto"),
            Coluna("Último pedido", "data"),
            Coluna("Dias sem comprar", "inteiro"),
            Coluna("Produtos", "texto"),
        ],
        [[c["nome"], c["ultimo_pedido"], c["dias"], ", ".join(c["produtos"])] for c in clientes],
        pedidos_a_repetir=[c["ultimo_pedido_id"] for c in clientes],
    )


def _tabela_vendas(pontos: list[dict]) -> Tabela:
    return Tabela(
        "Vendas por período",
        [
            Coluna("Período", "texto"),
            Coluna("Pedidos", "inteiro"),
            Coluna("Bruto", "dinheiro"),
            Coluna("Descontos", "dinheiro"),
            Coluna("Líquido", "dinheiro"),
            Coluna("Lucro", "dinheiro"),
            Coluna("Margem", "percentual"),
            Coluna("Valor médio", "dinheiro"),
        ],
        [
            [
                p["rotulo"],
                p["pedidos"],
                p["bruto"],
                p["descontos"],
                p["liquido"],
                p["lucro"],
                p["margem"],
                p["ticket"] or ZERO,
            ]  # fmt: skip
            for p in pontos
        ],
    )


def _resumo(f: Filtros, hoje: date) -> Relatorio:
    comparacao = comparar(f)
    atual = comparacao.atual
    pontos = serie(f)
    mais_vendidos = top_produtos(f)
    tabelas = [
        Tabela(
            "Indicadores",
            [
                Coluna("Faturamento líquido", "dinheiro"),
                Coluna("Lucro bruto", "dinheiro"),
                Coluna("Margem", "percentual"),
                Coluna("Pedidos", "inteiro"),
                Coluna("Valor médio por pedido", "dinheiro"),
            ],
            [
                [
                    atual.faturamento,
                    atual.lucro,
                    atual.margem,
                    atual.pedidos,
                    atual.ticket_medio or ZERO,
                ]
            ],
        ),
        _tabela_vendas(pontos),
        Tabela(
            "Produtos que mais faturaram",
            [
                Coluna("Código", "texto"),
                Coluna("Descrição", "texto"),
                Coluna("Quantidade", "inteiro"),
                Coluna("Faturamento", "dinheiro"),
                Coluna("Lucro", "dinheiro"),
                Coluna("Margem", "percentual"),
            ],
            [
                [
                    p["codigo"],
                    p["descricao"],
                    p["quantidade"],
                    p["faturamento"],
                    p["lucro"],
                    p["margem"],
                ]
                for p in mais_vendidos
            ],
        ),
        _tabela_sem_comprar(60, hoje, f, "Clientes sem comprar há mais de 60 dias"),
    ]
    graficos = {"serie": pontos, "produtos": mais_vendidos}
    return Relatorio("resumo", ABAS["resumo"], tabelas, comparacao, graficos)


def _tabelas_clientes(f: Filtros, hoje: date, dias: int) -> list[Tabela]:
    ranking = Tabela(
        "Ranking de clientes",
        [
            Coluna("Cliente", "texto"),
            Coluna("Valor", "dinheiro"),
            Coluna("Pedidos", "inteiro"),
            Coluna("Lucro", "dinheiro"),
            Coluna("Último pedido", "data"),
        ],
        [
            [c["nome"], c["valor"], c["pedidos"], c["lucro"], c["ultimo_pedido"]]
            for c in ranking_clientes(f)
        ],
    )
    sem_comprar = _tabela_sem_comprar(dias, hoje, f, f"Clientes sem comprar há mais de {dias} dias")
    return [ranking, sem_comprar]


def _tabelas_produtos(f: Filtros) -> list[Tabela]:
    metricas = [
        Coluna("Quantidade", "inteiro"),
        Coluna("Faturamento", "dinheiro"),
        Coluna("Lucro", "dinheiro"),
        Coluna("Margem", "percentual"),
        Coluna("Participação", "percentual"),
    ]

    def valores(x: dict) -> list[object]:
        return [x["quantidade"], x["faturamento"], x["lucro"], x["margem"], x["participacao"]]

    return [
        Tabela(
            "Por produto",
            [
                Coluna("Código", "texto"),
                Coluna("Descrição", "texto"),
                Coluna("Marca", "texto"),
                *metricas,
            ],
            [[p["codigo"], p["descricao"], p["marca"], *valores(p)] for p in produtos(f)],
        ),
        Tabela(
            "Por marca",
            [Coluna("Marca", "texto"), *metricas],
            [[m["marca"], *valores(m)] for m in marcas(f)],
        ),
    ]


def _tabelas_funcionarios(f: Filtros) -> list[Tabela]:
    return [
        Tabela(
            "Funcionários",
            [
                Coluna("Funcionário", "texto"),
                Coluna("Pedidos", "inteiro"),
                Coluna("Valor", "dinheiro"),
                Coluna("Lucro", "dinheiro"),
                Coluna("Desconto médio", "percentual"),
            ],
            [
                [x["nome"], x["pedidos"], x["valor"], x["lucro"], x["desconto_medio"]]
                for x in funcionarios(f)
            ],
        )
    ]


def _tabelas_estoque(f: Filtros) -> list[Tabela]:
    dados = estoque(f)
    rotulos = {
        "entradas": "Entradas (inclui estoque inicial)",
        "saidas": "Saídas",
        "devolucoes": "Devoluções",
        "ajustes_mais": "Ajustes (+)",
        "ajustes_menos": "Ajustes (−)",
    }
    return [
        Tabela(
            "Estoque atual",
            [
                Coluna("Código", "texto"),
                Coluna("Descrição", "texto"),
                Coluna("Estoque", "inteiro"),
                Coluna("Custo médio", "dinheiro"),
                Coluna("Valor em estoque", "dinheiro"),
            ],
            [
                [p["codigo"], p["descricao"], p["estoque"], p["custo_medio"], p["valor_em_estoque"]]
                for p in dados["produtos"]
            ],
        ),
        Tabela(
            "Valor total em estoque",
            [Coluna("Valor total em estoque", "dinheiro")],
            [[dados["valor_total"]]],
        ),
        Tabela("Produtos zerados", [Coluna("Código", "texto")], [[c] for c in dados["zerados"]]),
        Tabela(
            "Movimentos no período",
            [Coluna("Movimento", "texto"), Coluna("Quantidade", "inteiro")],
            [[rotulos[nome], quantidade] for nome, quantidade in dados["movimentos"].items()],
        ),
    ]


def _tabelas_cancelamentos(f: Filtros) -> list[Tabela]:
    return [
        Tabela(
            "Pedidos cancelados",
            [
                Coluna("Pedido", "inteiro"),
                Coluna("Cliente", "texto"),
                Coluna("Valor", "dinheiro"),
                Coluna("Motivo", "texto"),
                Coluna("Cancelado por", "texto"),
                Coluna("Data do cancelamento", "data"),
                Coluna("Emitido por", "texto"),
            ],
            [
                [
                    c["numero"],
                    c["cliente"],
                    c["valor"],
                    c["motivo"],
                    c["cancelado_por"],
                    c["cancelado_em"].astimezone(FUSO).date(),
                    c["emitido_por"],
                ]  # fmt: skip
                for c in cancelamentos(f)
            ],
        )
    ]


def montar_aba(aba: str, f: Filtros, hoje: date, dias_sem_comprar: int = 60) -> Relatorio:
    """Monta as tabelas (e, no Resumo, os dados dos gráficos) que a tela e as exportações usam."""
    if aba == "resumo":
        return _resumo(f, hoje)
    construtores = {
        "vendas": lambda: [_tabela_vendas(serie(f))],
        "clientes": lambda: _tabelas_clientes(f, hoje, dias_sem_comprar),
        "produtos": lambda: _tabelas_produtos(f),
        "funcionarios": lambda: _tabelas_funcionarios(f),
        "estoque": lambda: _tabelas_estoque(f),
        "cancelamentos": lambda: _tabelas_cancelamentos(f),
    }
    return Relatorio(aba, ABAS[aba], construtores[aba]())
