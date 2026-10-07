"""Regras do pedido: rascunho, confirmação, cancelamento e repetição (§3.1 a §3.5).

Toda edição abre uma transação e trava a linha do pedido (`_rascunho_para_editar`). Assim, duas
abas mexendo no mesmo rascunho são atendidas uma depois da outra. Ordem das travas, que vale
também para a confirmação e o cancelamento: pedido, depois produtos em ordem de id, depois o
contador.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.cadastros.models import Cliente, Produto
from apps.core.dinheiro import arredondar
from apps.core.erros import EstoqueInsuficiente, RegraDeNegocio
from apps.core.formatacao import inteiro_br
from apps.core.permissoes import eh_administrador, exigir_administrador
from apps.estoque.services import registrar_devolucao_pedido, registrar_saida_pedido

from .calculos import (
    DESCONTO_PERCENTUAL,
    DESCONTO_REAIS,
    Linha,
    Totais,
    calcular_totais,
    ratear_desconto,
)
from .models import ContadorPedido, ItemPedido, Pedido

QUANTIDADE_MAXIMA = 9999
OBSERVACOES_MAXIMO = 1000
MOTIVO_MAXIMO = 500

# Também usadas pelo formulário do item (apps/pedidos/forms.py).
MSG_QUANTIDADE = "Informe uma quantidade inteira maior que zero."
MSG_QUANTIDADE_MAXIMA = f"Quantidade máxima por item: {inteiro_br(QUANTIDADE_MAXIMA)}."

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
        raise RegraDeNegocio(MSG_QUANTIDADE)
    if quantidade > QUANTIDADE_MAXIMA:
        raise RegraDeNegocio(MSG_QUANTIDADE_MAXIMA)


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
            raise RegraDeNegocio(MSG_QUANTIDADE_MAXIMA)
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


def mudar_quantidade(pedido_id: int, item_id: int, passo: int, usuario) -> ItemPedido:
    """Soma `passo` (1 no botão +, -1 no −) à quantidade gravada na linha.

    A quantidade é lida com o pedido já travado: dois cliques seguidos, ou duas abas, contam
    os dois. As regras são as de `alterar_quantidade`.
    """
    with transaction.atomic():
        pedido = _rascunho_para_editar(pedido_id, usuario)
        item = _item_para_editar(pedido, item_id)
        return alterar_quantidade(pedido_id, item_id, item.quantidade + passo, usuario)


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
    # O caractere nulo sai: o PostgreSQL não aceita texto com ele.
    texto = (texto or "").replace("\x00", "").strip()
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


@dataclass(frozen=True)
class MudancaPreco:
    codigo: str
    descricao: str
    preco_anterior: Decimal
    preco_novo: Decimal


class ConfirmacaoRecusada(RegraDeNegocio):
    """O rascunho não pode ser confirmado agora; nada foi gravado."""

    def __init__(self, motivos: list[str]):
        super().__init__(" ".join(motivos))
        self.motivos = list(motivos)


class PrecosAlterados(RegraDeNegocio):
    """Algum preço mudou: o rascunho foi atualizado e gravado, mas não foi confirmado (§3.2)."""

    def __init__(self, mudancas: list[MudancaPreco]):
        super().__init__(
            "Os preços de alguns produtos mudaram. Confira o novo total e confirme de novo."
        )
        self.mudancas = list(mudancas)


def confirmar_pedido(pedido_id: int, usuario) -> Pedido:
    """Confirma o rascunho numa operação única: ou tudo é gravado, ou nada é (§3.1).

    Se algum preço mudou desde que o item entrou no rascunho, os itens passam para o preço atual
    e os totais são recalculados e gravados, mas o pedido não é confirmado. Por isso
    `PrecosAlterados` só é levantada depois do bloco atômico: dentro dele, desfaria a atualização.
    """
    with transaction.atomic():
        pedido = _rascunho_para_editar(pedido_id, usuario)
        itens = list(pedido.itens.all())
        motivos = []
        if pedido.cliente_id is None:
            motivos.append("Escolha o cliente antes de confirmar.")
        if not itens:
            motivos.append("Adicione pelo menos um produto.")
        if motivos:
            raise ConfirmacaoRecusada(motivos)

        # 1. Trava os produtos em ordem de id.
        produtos = _travar_produtos(itens)

        # 2. Cliente e produtos continuam ativos (§3.7, §3.8).
        if not pedido.cliente.ativo:
            motivos.append(f"O cliente {pedido.cliente.nome} foi inativado. Escolha outro cliente.")
        motivos += [
            f"O produto {item.codigo} foi inativado. Remova-o do pedido."
            for item in itens
            if not produtos[item.produto_id].ativo
        ]
        if motivos:
            raise ConfirmacaoRecusada(motivos)

        # 3. Preço de cada item igual ao do cadastro (§3.2).
        mudancas = _atualizar_precos(itens, produtos)
        if mudancas:
            _recalcular(pedido)
        else:
            _efetivar(pedido, itens, produtos, usuario)
    if mudancas:
        raise PrecosAlterados(mudancas)
    return pedido


def _travar_produtos(itens: list[ItemPedido]) -> dict[int, Produto]:
    """Trava os produtos dos itens em ordem de id e os devolve por id.

    A ordem fixa evita que duas operações (confirmação ou cancelamento) se travem em cruz.
    FOR NO KEY UPDATE: estoque e custo não são chaves, então a trava não espera quem só insere
    itens de rascunho apontando para o produto (a chave estrangeira pega FOR KEY SHARE).
    """
    travados = Produto.objects.select_for_update(no_key=True).filter(
        pk__in=[item.produto_id for item in itens]
    )
    return {produto.pk: produto for produto in travados.order_by("pk")}


def _atualizar_precos(itens: list[ItemPedido], produtos: dict[int, Produto]) -> list[MudancaPreco]:
    """Passa para o preço atual os itens cujo preço mudou e devolve o que mudou."""
    mudancas, alterados = [], []
    for item in itens:
        preco = produtos[item.produto_id].preco
        if item.preco_unitario != preco:
            mudancas.append(MudancaPreco(item.codigo, item.descricao, item.preco_unitario, preco))
            item.preco_unitario = preco
            alterados.append(item)
    ItemPedido.objects.bulk_update(alterados, ["preco_unitario"])
    return mudancas


def _efetivar(
    pedido: Pedido, itens: list[ItemPedido], produtos: dict[int, Produto], usuario
) -> None:
    """Passos 4 a 8 da confirmação, com os produtos já travados e os preços conferidos."""
    totais = _recalcular(pedido)
    # 4. Estoque de cada produto (cada produto aparece numa linha só do pedido).
    motivos = [
        f"Estoque insuficiente para {item.codigo}: "
        f"{inteiro_br(produtos[item.produto_id].estoque)} em estoque, "
        f"{inteiro_br(item.quantidade)} no pedido."
        for item in itens
        if item.quantidade > produtos[item.produto_id].estoque
    ]
    if totais.erro_desconto:
        motivos.append(totais.erro_desconto)
    if motivos:
        raise ConfirmacaoRecusada(motivos)

    # 5. Número sem buracos: se algo falhar depois daqui, o contador volta junto.
    contador = ContadorPedido.objects.select_for_update().get(pk=1)
    contador.ultimo_numero += 1
    contador.save(update_fields=["ultimo_numero"])

    # 6. e 7. Custo de cada item (o custo médio de agora) e saída do estoque (§3.5).
    partes = ratear_desconto([item.total for item in itens], totais.desconto_valor)
    for item, parte in zip(itens, partes, strict=True):
        produto = produtos[item.produto_id]
        item.custo_unitario = produto.custo_medio
        item.desconto_rateado = parte
        registrar_saida_pedido(
            produto=produto, quantidade=item.quantidade, pedido=pedido, usuario=usuario
        )
    ItemPedido.objects.bulk_update(itens, ["custo_unitario", "desconto_rateado"])

    # 8. Os totais já foram gravados por _recalcular; falta o status.
    pedido.numero = contador.ultimo_numero
    pedido.status = Pedido.Status.CONFIRMADO
    pedido.confirmado_por = usuario
    pedido.confirmado_em = timezone.now()
    pedido.save(
        update_fields=["numero", "status", "confirmado_por", "confirmado_em", "atualizado_em"]
    )


def cancelar_pedido(pedido_id: int, motivo: str, usuario) -> Pedido:
    """Cancela o pedido confirmado numa operação única e devolve o estoque (§3.1, §3.4, §3.5).

    Cada item volta pelo custo gravado nele na confirmação, que entra no custo médio como uma
    entrada. Número, totais e itens ficam como estavam.
    """
    exigir_administrador(usuario)
    motivo = (motivo or "").strip()
    if not motivo:
        raise RegraDeNegocio("Informe o motivo do cancelamento.")
    if len(motivo) > MOTIVO_MAXIMO:
        raise RegraDeNegocio(f"O motivo pode ter até {MOTIVO_MAXIMO} caracteres.")
    with transaction.atomic():
        # O status é lido com a trava: quem esperava outro cancelamento vê o pedido já cancelado.
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        if pedido.status != Pedido.Status.CONFIRMADO:
            raise RegraDeNegocio("Só pedidos confirmados podem ser cancelados.")
        itens = list(pedido.itens.all())
        produtos = _travar_produtos(itens)
        for item in itens:
            registrar_devolucao_pedido(
                produto=produtos[item.produto_id],
                quantidade=item.quantidade,
                custo_unitario=item.custo_unitario,
                pedido=pedido,
                usuario=usuario,
            )
        pedido.status = Pedido.Status.CANCELADO
        pedido.cancelado_por = usuario
        pedido.cancelado_em = timezone.now()
        pedido.motivo_cancelamento = motivo
        pedido.save(
            update_fields=[
                "status",
                "cancelado_por",
                "cancelado_em",
                "motivo_cancelamento",
                "atualizado_em",
            ]
        )
    return pedido


def repetir_pedido(pedido_id: int, usuario) -> Pedido:
    """Cria um rascunho de `usuario` com o cliente e os itens do pedido (§3.1, decisão P7).

    Os itens recebem o código, a descrição e o preço atuais do produto. Desconto e observações
    não são copiados. Produtos inativos ou sem estoque entram assim mesmo: os avisos do rascunho
    mostram o que impede a confirmação.
    """
    original = Pedido.objects.get(pk=pedido_id)
    if original.status not in (Pedido.Status.CONFIRMADO, Pedido.Status.CANCELADO):
        raise RegraDeNegocio("Só pedidos confirmados ou cancelados podem ser repetidos.")
    with transaction.atomic():
        novo = criar_rascunho(usuario)
        novo.cliente_id = original.cliente_id
        novo.save(update_fields=["cliente", "atualizado_em"])
        ItemPedido.objects.bulk_create(
            ItemPedido(
                pedido=novo,
                produto=item.produto,
                codigo=item.produto.codigo,
                descricao=item.produto.descricao,
                quantidade=item.quantidade,
                preco_unitario=item.produto.preco,
            )
            for item in original.itens.select_related("produto")
        )
        _recalcular(novo)
    return novo
