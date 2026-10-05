from django.contrib import admin

from .models import ItemPedido, Pedido


class SoLeitura:
    """Pedidos só mudam pelos serviços (travas, estoque e numeração); o painel só consulta."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ItemPedidoInline(SoLeitura, admin.TabularInline):
    model = ItemPedido
    extra = 0


@admin.register(Pedido)
class PedidoAdmin(SoLeitura, admin.ModelAdmin):
    list_display = ("id", "numero", "status", "cliente", "criado_por", "total", "criado_em")
    list_filter = ("status",)
    search_fields = ("numero", "cliente__nome")
    inlines = [ItemPedidoInline]
