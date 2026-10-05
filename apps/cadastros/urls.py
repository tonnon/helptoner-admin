from django.urls import path

from . import views

app_name = "cadastros"

urlpatterns = [
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/novo/", views.cliente_novo, name="cliente_novo"),
    path("clientes/<int:pk>/", views.cliente_editar, name="cliente_editar"),
    path("clientes/<int:pk>/inativar/", views.cliente_inativar, name="cliente_inativar"),
    path("clientes/<int:pk>/reativar/", views.cliente_reativar, name="cliente_reativar"),
]
