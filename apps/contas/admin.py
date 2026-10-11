from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import RegistroAcesso, Usuario


@admin.register(Usuario)
class UsuarioAdmin(SimpleHistoryAdmin):
    list_display = ("email", "nome", "is_active")
    search_fields = ("email", "nome")
    ordering = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "nome")}),
        ("Situação", {"fields": ("is_active", "is_staff", "deve_trocar_senha")}),
        ("Perfis", {"fields": ("groups",)}),
    )


@admin.register(RegistroAcesso)
class RegistroAcessoAdmin(admin.ModelAdmin):
    """Registro de acessos só para leitura: ninguém cria, muda ou apaga, nem pelo painel."""

    list_display = ("quando", "email_tentado", "sucesso", "motivo", "ip", "navegador")
    list_filter = ("sucesso",)
    search_fields = ("email_tentado",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
