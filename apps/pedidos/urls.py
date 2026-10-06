from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [
    path("pedidos/", views.lista, name="lista"),
    path("pedidos/<int:pk>/", views.detalhe, name="detalhe"),
    path("pedidos/<int:pk>/cancelar/", views.cancelar, name="cancelar"),
]
