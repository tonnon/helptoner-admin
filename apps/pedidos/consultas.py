import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.db.models import QuerySet
from django.db.models.functions import Coalesce

from apps.cadastros.buscas import normalizar_busca
from apps.cadastros.models import Cliente
from apps.core.datas import intervalo_de_datas, mes_de
from apps.core.dinheiro import arredondar
from apps.core.formatacao import inteiro_br

from .calculos import Linha, calcular_totais, margem
from .models import Pedido

_NUMERO_MAXIMO = 2_147_483_647  # maior valor do campo numero (inteiro do PostgreSQL)


@dataclass(frozen=True)
class Avisos:
    gerais: list[str]
    por_item: dict[int, str]  # id do item → aviso da linha
    erro_desconto: str | None


def avisos_do_rascunho(pedido: Pedido) -> Avisos:
    """O que impede a confirmação do rascunho, lido do banco agora (§3.2, §3.3, §3.7, §3.8)."""
    gerais = []
    if pedido.cliente_id is not None:
        cliente = Cliente.objects.only("nome", "ativo").get(pk=pedido.cliente_id)
        if not cliente.ativo:
            gerais.append(f"O cliente {cliente.nome} foi inativado. Escolha outro cliente.")

    itens = list(pedido.itens.select_related("produto"))
    por_item = {}
    for item in itens:
        produto = item.produto
        if not produto.ativo:
            por_item[item.pk] = f"O produto {item.codigo} foi inativado. Remova-o do pedido."
        elif produto.estoque == 0:
            por_item[item.pk] = "Sem estoque."
        elif item.quantidade > produto.estoque:
            por_item[item.pk] = f"Só há {inteiro_br(produto.estoque)} em estoque."

    totais = calcular_totais(
        [Linha(item.quantidade, item.preco_unitario) for item in itens],
        pedido.desconto_tipo,
        pedido.desconto_informado,
    )
    return Avisos(gerais, por_item, totais.erro_desconto)


def _numero_da_busca(busca: str) -> int | None:
    """ "1.042", "1042" e "nº 1042" viram 1042; qualquer outra coisa é busca por cliente."""
    digitos = re.sub(r"[nº°.\s]", "", busca, flags=re.IGNORECASE)
    return int(digitos) if re.fullmatch(r"[0-9]+", digitos) else None


def _mes_valido(mes: str) -> date | None:
    try:
        return datetime.strptime(mes, "%Y-%m").date()
    except ValueError:
        return None


def filtrar_pedidos(*, busca: str = "", status: str = "", mes: str = "") -> QuerySet[Pedido]:
    """Pedidos por número ou cliente, status e mês (de Brasília), do mais recente ao mais antigo.

    A data de referência é a confirmação ou, no rascunho, a criação. Filtros inválidos
    (status desconhecido, mês fora de "AAAA-MM") são ignorados.
    """
    pedidos = (
        Pedido.objects.select_related("cliente", "criado_por")
        .annotate(data_referencia=Coalesce("confirmado_em", "criado_em"))
        .order_by("-data_referencia", "-id")
    )
    busca = normalizar_busca(busca)
    if busca:
        numero = _numero_da_busca(busca)
        if numero is None:
            pedidos = pedidos.filter(cliente__nome__unaccent__icontains=busca)
        elif numero > _NUMERO_MAXIMO:
            return pedidos.none()
        else:
            pedidos = pedidos.filter(numero=numero)
    if status in Pedido.Status.values:
        pedidos = pedidos.filter(status=status)
    primeiro_dia = _mes_valido(mes)
    if primeiro_dia is not None:
        inicio, fim = intervalo_de_datas(*mes_de(primeiro_dia))
        pedidos = pedidos.filter(data_referencia__gte=inicio, data_referencia__lt=fim)
    return pedidos


def lucro_do_pedido(pedido: Pedido) -> tuple[Decimal, Decimal | None]:
    """Lucro bruto (total menos o custo gravado nos itens) e margem sobre o total (§3.5)."""
    custo = sum(
        ((item.custo_unitario or Decimal("0")) * item.quantidade for item in pedido.itens.all()),
        Decimal("0"),
    )
    lucro = pedido.total - custo
    return arredondar(lucro), margem(lucro, pedido.total)
