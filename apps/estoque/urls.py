from django.urls import path

from . import views

app_name = "estoque"

urlpatterns = [
    path("estoque/", views.historico, name="historico"),
    path("estoque/entrada/", views.entrada, name="entrada"),
    path("estoque/inicial/", views.inicial, name="inicial"),
    path("estoque/ajuste/", views.ajuste, name="ajuste"),
]
