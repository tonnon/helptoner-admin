from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from apps.cadastros.models import Produto
from apps.core.dinheiro import arredondar_custo
from apps.core.erros import EstoqueInsuficiente, RegraDeNegocio
from apps.core.permissoes import exigir_administrador

from .models import MovimentoEstoque

if TYPE_CHECKING:
    from apps.pedidos.models import Pedido

Tipo = MovimentoEstoque.Tipo

_ENTRAM_NA_MEDIA = {Tipo.INICIAL, Tipo.ENTRADA, Tipo.DEVOLUCAO}
_ENTRAM_NO_ESTOQUE = _ENTRAM_NA_MEDIA | {Tipo.AJUSTE_MAIS}

_MSG_QUANTIDADE = "Informe uma quantidade inteira maior que zero."
_MSG_CUSTO = "Informe o custo unitário (maior que zero)."


def novo_custo_medio(
    estoque_atual: int, custo_atual: Decimal, quantidade: int, custo_entrada: Decimal
) -> Decimal:
    """Custo médio ponderado depois de uma entrada, com 4 casas (meio para cima)."""
    total = estoque_atual + quantidade
    if total == 0:
        return arredondar_custo(custo_atual)
    return arredondar_custo((estoque_atual * custo_atual + quantidade * custo_entrada) / total)


def _validar_quantidade(quantidade) -> None:
    if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade <= 0:
        raise RegraDeNegocio(_MSG_QUANTIDADE)


def _validar_custo(custo_unitario) -> None:
    if not isinstance(custo_unitario, Decimal) or not custo_unitario > 0:
        raise RegraDeNegocio(_MSG_CUSTO)


def _travar(produto_id: int) -> Produto:
    return Produto.objects.select_for_update().get(pk=produto_id)


def _aplicar_movimento(
    produto: Produto,
    *,
    tipo: str,
    quantidade: int,
    custo_unitario: Decimal,
    usuario,
    motivo: str = "",
    **extra,
) -> MovimentoEstoque:
    """Aplica um movimento ao produto, que já deve estar travado na transação atual."""
    if tipo in _ENTRAM_NO_ESTOQUE:
        estoque = produto.estoque + quantidade
    else:
        estoque = produto.estoque - quantidade
    if estoque < 0:
        raise EstoqueInsuficiente(
            f"O estoque atual é {produto.estoque}; a quantidade pedida é {quantidade}."
        )
    if tipo in _ENTRAM_NA_MEDIA:
        custo_medio = novo_custo_medio(
            produto.estoque, produto.custo_medio, quantidade, custo_unitario
        )
    else:
        custo_medio = produto.custo_medio
    movimento = MovimentoEstoque.objects.create(
        produto=produto,
        tipo=tipo,
        quantidade=quantidade,
        custo_unitario=custo_unitario,
        estoque_apos=estoque,
        custo_medio_apos=custo_medio,
        usuario=usuario,
        motivo=motivo,
        **extra,
    )
    # update() em vez de save(): estoque e custo médio não entram no histórico do produto.
    Produto.objects.filter(pk=produto.pk).update(estoque=estoque, custo_medio=custo_medio)
    produto.estoque = estoque
    produto.custo_medio = custo_medio
    return movimento


def registrar_estoque_inicial(
    *, produto_id: int, quantidade: int, custo_unitario: Decimal, usuario
) -> MovimentoEstoque:
    exigir_administrador(usuario)
    _validar_quantidade(quantidade)
    _validar_custo(custo_unitario)
    with transaction.atomic():
        produto = _travar(produto_id)
        if produto.movimentos.exists():
            raise RegraDeNegocio("Este produto já tem movimentos. Use Entrada.")
        return _aplicar_movimento(
            produto,
            tipo=Tipo.INICIAL,
            quantidade=quantidade,
            custo_unitario=custo_unitario,
            usuario=usuario,
        )


def registrar_entrada(
    *, produto_id: int, quantidade: int, custo_unitario: Decimal, observacao: str, usuario
) -> MovimentoEstoque:
    exigir_administrador(usuario)
    observacao = (observacao or "").strip()
    if not observacao:
        raise RegraDeNegocio("Informe a observação (ex.: nº da nota).")
    _validar_custo(custo_unitario)
    _validar_quantidade(quantidade)
    with transaction.atomic():
        produto = _travar(produto_id)
        return _aplicar_movimento(
            produto,
            tipo=Tipo.ENTRADA,
            quantidade=quantidade,
            custo_unitario=custo_unitario,
            usuario=usuario,
            motivo=observacao,
        )


def registrar_saida_pedido(
    *, produto: Produto, quantidade: int, pedido: Pedido, usuario
) -> MovimentoEstoque:
    """Saída por pedido, feita pela confirmação, que já travou o produto e conferiu o estoque.

    O custo médio não muda; o movimento grava o custo médio do momento (§3.5).
    """
    return _aplicar_movimento(
        produto,
        tipo=Tipo.SAIDA,
        quantidade=quantidade,
        custo_unitario=produto.custo_medio,
        usuario=usuario,
        pedido=pedido,
    )


def registrar_ajuste(*, produto_id: int, delta: int, motivo: str, usuario) -> MovimentoEstoque:
    exigir_administrador(usuario)
    motivo = (motivo or "").strip()
    if not motivo:
        raise RegraDeNegocio("Informe o motivo do ajuste.")
    if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
        raise RegraDeNegocio(_MSG_QUANTIDADE)
    with transaction.atomic():
        produto = _travar(produto_id)
        if delta > 0:
            tem_custo = produto.movimentos.filter(tipo__in=[Tipo.INICIAL, Tipo.ENTRADA]).exists()
            if not tem_custo:
                raise RegraDeNegocio(
                    "Este produto ainda não tem custo. "
                    "Lance o estoque inicial ou uma entrada antes do ajuste."
                )
            tipo = Tipo.AJUSTE_MAIS
        else:
            tipo = Tipo.AJUSTE_MENOS
        try:
            return _aplicar_movimento(
                produto,
                tipo=tipo,
                quantidade=abs(delta),
                custo_unitario=produto.custo_medio,
                usuario=usuario,
                motivo=motivo,
            )
        except EstoqueInsuficiente:
            raise EstoqueInsuficiente(
                f"O estoque atual é {produto.estoque}; o ajuste deixaria o estoque negativo."
            ) from None
