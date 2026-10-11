from django.contrib import admin

from .models import MovimentoEstoque


@admin.register(MovimentoEstoque)
class MovimentoEstoqueAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "produto", "tipo", "quantidade", "estoque_apos", "usuario")
    list_filter = ("tipo",)
    search_fields = ("produto__codigo", "produto__descricao")

    # O livro de movimentos é só de consulta: quem grava são os serviços.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
