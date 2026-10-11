from django.urls import path

from . import views

app_name = "cadastros"

urlpatterns = [
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/novo/", views.cliente_novo, name="cliente_novo"),
    path("clientes/<int:pk>/", views.cliente_editar, name="cliente_editar"),
    path("clientes/<int:pk>/inativar/", views.cliente_inativar, name="cliente_inativar"),
    path("clientes/<int:pk>/reativar/", views.cliente_reativar, name="cliente_reativar"),
    path("produtos/", views.produtos, name="produtos"),
    path("produtos/novo/", views.produto_novo, name="produto_novo"),
    path("produtos/<int:pk>/", views.produto_editar, name="produto_editar"),
    path("produtos/<int:pk>/inativar/", views.produto_inativar, name="produto_inativar"),
    path("produtos/<int:pk>/reativar/", views.produto_reativar, name="produto_reativar"),
]
