"""Consultas dos relatórios: indicadores, comparação, série temporal, produtos e clientes."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, QuerySet, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek

from apps.core.datas import FUSO, intervalo_de_datas
from apps.core.dinheiro import arredondar
from apps.pedidos.calculos import margem
from apps.pedidos.models import ItemPedido, Pedido
from apps.relatorios.periodos import (
    Agrupamento,
    Filtros,
    descricao_comparacao,
    periodo_anterior,
)

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
    """Clientes cujo último pedido confirmado (data de Brasília) é de mais de `dias` dias atrás."""
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
