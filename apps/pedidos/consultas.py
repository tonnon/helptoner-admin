from dataclasses import dataclass

from apps.cadastros.models import Cliente
from apps.core.formatacao import inteiro_br

from .calculos import Linha, calcular_totais
from .models import Pedido


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
