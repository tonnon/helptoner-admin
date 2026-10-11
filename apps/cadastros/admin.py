from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Cliente, Produto


@admin.register(Cliente)
class ClienteAdmin(SimpleHistoryAdmin):
    list_display = ("nome", "documento", "cidade", "uf", "ativo")
    search_fields = ("nome", "documento")
    list_filter = ("ativo", "tipo")


@admin.register(Produto)
class ProdutoAdmin(SimpleHistoryAdmin):
    list_display = ("codigo", "descricao", "marca", "preco", "estoque", "ativo")
    search_fields = ("codigo", "descricao", "marca")
    list_filter = ("ativo", "marca")
    # Estoque e custo médio só mudam por movimento de estoque (Tarefa 12).
    readonly_fields = ("estoque", "custo_medio")
