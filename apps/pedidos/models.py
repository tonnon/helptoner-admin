from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.cadastros.models import Cliente, Produto
from apps.core.formatacao import numero_pedido

from .calculos import DESCONTO_PERCENTUAL, DESCONTO_REAIS, Linha

_ZERO = Decimal("0")


class Pedido(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        CONFIRMADO = "confirmado", "Confirmado"
        CANCELADO = "cancelado", "Cancelado"

    class TipoDesconto(models.TextChoices):
        REAIS = DESCONTO_REAIS, "R$"
        PERCENTUAL = DESCONTO_PERCENTUAL, "%"

    # O número só nasce na confirmação (§3.1); o rascunho não tem número.
    numero = models.PositiveIntegerField("Número", null=True, blank=True, unique=True)
    status = models.CharField("Status", max_length=20, choices=Status, default=Status.RASCUNHO)
    cliente = models.ForeignKey(
        Cliente,
        verbose_name="Cliente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pedidos",
    )
    # Quem criou o rascunho é quem emitiu o pedido (decisão P5); o índice vem com a FK.
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Criado por",
        on_delete=models.PROTECT,
        related_name="pedidos_criados",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Confirmado por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    confirmado_em = models.DateTimeField("Confirmado em", null=True, blank=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Cancelado por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    cancelado_em = models.DateTimeField("Cancelado em", null=True, blank=True)
    motivo_cancelamento = models.TextField("Motivo do cancelamento", blank=True)
    desconto_tipo = models.CharField(
        "Tipo de desconto",
        max_length=10,
        choices=TipoDesconto,
        default=TipoDesconto.PERCENTUAL,
    )
    desconto_informado = models.DecimalField(
        "Desconto informado", max_digits=12, decimal_places=2, default=_ZERO
    )
    desconto_valor = models.DecimalField(
        "Desconto (R$)", max_digits=12, decimal_places=2, default=_ZERO
    )
    subtotal = models.DecimalField("Subtotal", max_digits=12, decimal_places=2, default=_ZERO)
    total = models.DecimalField("Total", max_digits=12, decimal_places=2, default=_ZERO)
    observacoes = models.TextField("Observações", max_length=1000, blank=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status="rascunho", numero__isnull=True)
                    | (~models.Q(status="rascunho") & models.Q(numero__isnull=False))
                ),
                name="pedido_numero_so_fora_do_rascunho",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    desconto_informado__gte=0,
                    desconto_valor__gte=0,
                    subtotal__gte=0,
                    total__gte=0,
                ),
                name="pedido_valores_nao_negativos",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "confirmado_em"], name="pedido_status_confirmado_idx"),
        ]

    def __str__(self):
        if self.numero is None:
            return f"Rascunho {self.pk}"
        return f"Pedido {numero_pedido(self.numero)}"


class ItemPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido, verbose_name="Pedido", on_delete=models.CASCADE, related_name="itens"
    )
    produto = models.ForeignKey(
        Produto, verbose_name="Produto", on_delete=models.PROTECT, related_name="itens_de_pedido"
    )
    # Código, descrição e preço são copiados do produto ao adicionar; o custo, na confirmação.
    codigo = models.CharField("Código", max_length=30)
    descricao = models.CharField("Descrição", max_length=200)
    quantidade = models.PositiveIntegerField("Quantidade")
    preco_unitario = models.DecimalField("Preço unitário", max_digits=12, decimal_places=2)
    custo_unitario = models.DecimalField(
        "Custo unitário", max_digits=14, decimal_places=4, null=True, blank=True
    )
    desconto_rateado = models.DecimalField(
        "Desconto rateado", max_digits=12, decimal_places=2, default=_ZERO
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade__gt=0), name="item_quantidade_positiva"
            ),
            models.UniqueConstraint(
                fields=["pedido", "produto"], name="item_produto_unico_no_pedido"
            ),
        ]

    def __str__(self):
        return f"{self.quantidade} × {self.codigo}"

    @property
    def total(self) -> Decimal:
        return Linha(self.quantidade, self.preco_unitario).total


class ContadorPedido(models.Model):
    """Linha única com o último número de pedido, travada na confirmação (§3.1)."""

    ultimo_numero = models.PositiveIntegerField("Último número", default=0)

    class Meta:
        verbose_name = "contador de pedidos"
        verbose_name_plural = "contador de pedidos"
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="contador_pedido_linha_unica"),
        ]

    def __str__(self):
        return f"Último número: {self.ultimo_numero}"
