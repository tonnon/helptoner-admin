from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [
    path("pedidos/", views.lista, name="lista"),
    path("pedidos/novo/", views.novo, name="novo"),
    path("pedidos/<int:pk>/", views.detalhe, name="detalhe"),
    path("pedidos/<int:pk>/pdf/", views.baixar_pdf, name="pdf"),
    path("pedidos/<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("pedidos/<int:pk>/repetir/", views.repetir, name="repetir"),
    # Editor do rascunho
    path("pedidos/<int:pk>/editar/", views.editar, name="editar"),
    path(
        "pedidos/<int:pk>/sugestoes/clientes/",
        views.sugestoes_cliente,
        name="sugestoes_cliente",
    ),
    path(
        "pedidos/<int:pk>/sugestoes/produtos/",
        views.sugestoes_produto,
        name="sugestoes_produto",
    ),
    path("pedidos/<int:pk>/cliente/", views.definir_cliente, name="definir_cliente"),
    path("pedidos/<int:pk>/itens/", views.adicionar_item, name="adicionar_item"),
    path(
        "pedidos/<int:pk>/itens/<int:item_id>/quantidade/",
        views.alterar_quantidade,
        name="alterar_quantidade",
    ),
    path(
        "pedidos/<int:pk>/itens/<int:item_id>/remover/",
        views.remover_item,
        name="remover_item",
    ),
    path("pedidos/<int:pk>/desconto/", views.definir_desconto, name="definir_desconto"),
    path("pedidos/<int:pk>/observacoes/", views.definir_observacoes, name="definir_observacoes"),
    path("pedidos/<int:pk>/confirmar/", views.confirmar, name="confirmar"),
    path("pedidos/<int:pk>/excluir/", views.excluir, name="excluir"),
]
