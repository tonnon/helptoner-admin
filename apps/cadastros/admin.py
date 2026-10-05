from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(SimpleHistoryAdmin):
    list_display = ("nome", "documento", "cidade", "uf", "ativo")
    search_fields = ("nome", "documento")
    list_filter = ("ativo", "tipo")
