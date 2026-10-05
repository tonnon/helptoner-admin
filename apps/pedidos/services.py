"""Regras do pedido em rascunho (§3.1 a §3.3).

Toda edição abre uma transação e trava a linha do pedido (`_rascunho_para_editar`). Assim, duas
abas mexendo no mesmo rascunho são atendidas uma depois da outra. Ordem das travas, que vale
também para a confirmação e o cancelamento: pedido, depois produtos em ordem de id, depois o
contador.
"""

from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.cadastros.models import Cliente, Produto
from apps.core.dinheiro import arredondar
from apps.core.erros import EstoqueInsuficiente, RegraDeNegocio
from apps.core.formatacao import inteiro_br
from apps.core.permissoes import eh_administrador

from .calculos import DESCONTO_PERCENTUAL, DESCONTO_REAIS, Linha, Totais, calcular_totais
from .models import ItemPedido, Pedido

QUANTIDADE_MAXIMA = 9999
OBSERVACOES_MAXIMO = 1000

_MSG_QUANTIDADE = "Informe uma quantidade inteira maior que zero."
_MSG_QUANTIDADE_MAXIMA = f"Quantidade máxima por item: {inteiro_br(QUANTIDADE_MAXIMA)}."

# Maior valor que cabe nos campos de dinheiro (12 dígitos, 2 casas).
_VALOR_MAXIMO = Decimal("9999999999.99")
_CEM = Decimal("100")


def pode_editar(pedido: Pedido, usuario) -> bool:
    """Rascunho só é editado por quem o criou ou por um Administrador (§3.1, decisão P6)."""
    return pedido.status == Pedido.Status.RASCUNHO and _pode_mexer(pedido, usuario)


def _pode_mexer(pedido: Pedido, usuario) -> bool:
    return pedido.criado_por_id == usuario.pk or eh_administrador(usuario)


def _rascunho_para_editar(pedido_id: int, usuario) -> Pedido:
    """Trava a linha do pedido até o fim da transação e confere se ele pode ser editado."""
    pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
    if not _pode_mexer(pedido, usuario):
        raise PermissionDenied
    if pedido.status != Pedido.Status.RASCUNHO:
        raise RegraDeNegocio("Este pedido não é mais um rascunho e não pode ser alterado.")
    return pedido


def _recalcular(pedido: Pedido) -> Totais:
    """Recalcula e grava subtotal, desconto e total a partir dos itens do pedido."""
    linhas = [
        Linha(q, preco) for q, preco in pedido.itens.values_list("quantidade", "preco_unitario")
    ]
    totais = calcular_totais(linhas, pedido.desconto_tipo, pedido.desconto_informado)
    pedido.subtotal = totais.subtotal
    pedido.desconto_valor = totais.desconto_valor
    pedido.total = totais.total
    pedido.save(update_fields=["subtotal", "desconto_valor", "total", "atualizado_em"])
    return totais


def _validar_quantidade(quantidade) -> None:
    if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade <= 0:
        raise RegraDeNegocio(_MSG_QUANTIDADE)
    if quantidade > QUANTIDADE_MAXIMA:
        raise RegraDeNegocio(_MSG_QUANTIDADE_MAXIMA)


def criar_rascunho(usuario) -> Pedido:
    return Pedido.objects.create(criado_por=usuario)


def definir_cliente(pedido_id: int, cliente_id: int, usuario) -> Pedido:
    with transaction.atomic():
        pedido = _rascunho_para_editar(pedido_id, usuario)
        cliente = Cliente.objects.get(pk=cliente_id)
        if not cliente.ativo:
            raise RegraDeNegocio("Este cliente está inativo. Escolha outro cliente.")
        pedido.cliente = cliente
        pedido.save(update_fields=["cliente", "atualizado_em"])
        return pedido


def adicionar_item(pedido_id: int, produto_id: int, quantidade: int, usuario) -> ItemPedido:
    """Adiciona o produto ao rascunho; se ele já está no pedido, soma na mesma linha (§3.2)."""
    _validar_quantidade(quantidade)
    with transaction.atomic():
        pedido = _rascunho_para_editar(pedido_id, usuario)
        produto = Produto.objects.get(pk=produto_id)
        if not produto.ativo:
            raise RegraDeNegocio("Este produto está inativo e não pode ser adicionado.")
        # Procurado depois da trava do pedido: a outra aba já gravou a linha, se ia gravar.
        item = pedido.itens.select_for_update().filter(produto=produto).first()
        ja_no_pedido = item.quantidade if item else 0
        nova = ja_no_pedido + quantidade
        if nova > produto.estoque:
            raise EstoqueInsuficiente(_falta_para_adicionar(produto.estoque, ja_no_pedido))
        if nova > QUANTIDADE_MAXIMA:
            raise RegraDeNegocio(_MSG_QUANTIDADE_MAXIMA)
        if item:
            item.quantidade = nova
            item.save(update_fields=["quantidade"])
        else:
            item = ItemPedido.objects.create(
                pedido=pedido,
                produto=produto,
                codigo=produto.codigo,
                descricao=produto.descricao,
                quantidade=quantidade,
                preco_unitario=produto.preco,
            )
        _recalcular(pedido)
        return item


def _falta_para_adicionar(estoque: int, ja_no_pedido: int) -> str:
    if not ja_no_pedido:
        return f"Estoque insuficiente: {inteiro_br(estoque)} em estoque."
    resta = max(estoque - ja_no_pedido, 0)
    return (
        f"Estoque insuficiente: {inteiro_br(estoque)} em estoque, "
        f"{inteiro_br(ja_no_pedido)} já no pedido (dá para adicionar mais {inteiro_br(resta)})."
    )


def _item_para_editar(pedido: Pedido, item_id: int) -> ItemPedido:
    item = pedido.itens.select_for_update().filter(pk=item_id).first()
    if item is None:
        raise RegraDeNegocio("Este item não está mais no pedido.")
    return item


def alterar_quantidade(pedido_id: int, item_id: int, quantidade: int, usuario) -> ItemPedido:
    """Muda a quantidade da linha. Só o aumento é conferido com o estoque."""
    _validar_quantidade(quantidade)
    with transaction.atomic():
        pedido = _rascunho_para_editar(pedido_id, usuario)
        item = _item_para_editar(pedido, item_id)
        estoque = Produto.objects.values_list("estoque", flat=True).get(pk=item.produto_id)
        if quantidade > item.quantidade and quantidade > estoque:
            raise EstoqueInsuficiente(
                f"Estoque insuficiente para {item.codigo}: {inteiro_br(estoque)} em estoque."
            )
        item.quantidade = quantidade
        item.save(update_fields=["quantidade"])
        _recalcular(pedido)
        return item


def remover_item(pedido_id: int, item_id: int, usuario) -> None:
    """Tira a linha do rascunho. Remover de novo (clique duplo, outra aba) não dá erro."""
    with transaction.atomic():
        pedido = _rascunho_para_editar(pedido_id, usuario)
        pedido.itens.filter(pk=item_id).delete()
        _recalcular(pedido)


def definir_desconto(pedido_id: int, tipo: str, valor: Decimal, usuario) -> Pedido:
    """Grava o desconto do pedido (§3.3).

    Desconto negativo ou acima de 100% é recusado. Desconto em R$ maior que o subtotal fica
    gravado: o total ignora o desconto e os avisos do rascunho mostram o erro (decisão P3).
    """
    if tipo not in (DESCONTO_REAIS, DESCONTO_PERCENTUAL):
        raise RegraDeNegocio("Tipo de desconto inválido.")
    if not isinstance(valor, Decimal) or not valor.is_finite():
        raise RegraDeNegocio("Informe um número. Ex.: 10 ou 10,5")
    if valor < 0:
        raise RegraDeNegocio("O desconto não pode ser negativo.")
    if tipo == DESCONTO_PERCENTUAL and valor > _CEM:
        raise RegraDeNegocio("O desconto não pode passar de 100%.")
    if valor > _VALOR_MAXIMO:
        raise RegraDeNegocio("O desconto não pode passar do subtotal.")
    with transaction.atomic():
        pedido = _rascunho_para_editar(pedido_id, usuario)
        pedido.desconto_tipo = tipo
        pedido.desconto_informado = arredondar(valor)
        pedido.save(update_fields=["desconto_tipo", "desconto_informado"])
        _recalcular(pedido)
        return pedido


def definir_observacoes(pedido_id: int, texto: str, usuario) -> Pedido:
    texto = (texto or "").strip()
    if len(texto) > OBSERVACOES_MAXIMO:
        raise RegraDeNegocio(
            f"As observações podem ter até {inteiro_br(OBSERVACOES_MAXIMO)} caracteres."
        )
    with transaction.atomic():
        pedido = _rascunho_para_editar(pedido_id, usuario)
        pedido.observacoes = texto
        pedido.save(update_fields=["observacoes", "atualizado_em"])
        return pedido


def excluir_rascunho(pedido_id: int, usuario) -> None:
    with transaction.atomic():
        _rascunho_para_editar(pedido_id, usuario).delete()
