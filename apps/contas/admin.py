from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Usuario


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
