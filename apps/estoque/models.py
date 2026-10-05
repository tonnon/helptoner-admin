from django.conf import settings
from django.db import models

from apps.cadastros.models import Produto


class MovimentoEstoque(models.Model):
    class Tipo(models.TextChoices):
        INICIAL = "inicial", "Estoque inicial"
        ENTRADA = "entrada", "Entrada"
        SAIDA = "saida", "Saída por pedido"
        DEVOLUCAO = "devolucao", "Devolução por cancelamento"
        AJUSTE_MAIS = "ajuste_mais", "Ajuste (+)"
        AJUSTE_MENOS = "ajuste_menos", "Ajuste (−)"

    produto = models.ForeignKey(
        Produto,
        verbose_name="Produto",
        on_delete=models.PROTECT,
        related_name="movimentos",
    )
    tipo = models.CharField("Tipo", max_length=20, choices=Tipo)
    quantidade = models.PositiveIntegerField("Quantidade")
    custo_unitario = models.DecimalField("Custo unitário", max_digits=14, decimal_places=4)
    estoque_apos = models.IntegerField("Estoque após o movimento")
    custo_medio_apos = models.DecimalField(
        "Custo médio após o movimento", max_digits=14, decimal_places=4
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Usuário",
        on_delete=models.PROTECT,
        related_name="+",
    )
    motivo = models.CharField("Observação ou motivo", max_length=200, blank=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "movimento de estoque"
        verbose_name_plural = "movimentos de estoque"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade__gt=0), name="movimento_quantidade_positiva"
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.quantidade} ({self.produto})"
