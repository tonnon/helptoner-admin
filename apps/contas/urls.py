from django.urls import path

from . import views

app_name = "contas"

urlpatterns = [
    path("primeiro-acesso/senha/", views.primeiro_acesso_senha, name="primeiro_acesso_senha"),
    path(
        "primeiro-acesso/concluir/",
        views.primeiro_acesso_concluir,
        name="primeiro_acesso_concluir",
    ),
    path("minha-conta/", views.minha_conta, name="minha_conta"),
]
