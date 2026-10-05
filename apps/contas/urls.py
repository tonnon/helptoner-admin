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
    path("funcionarios/", views.funcionarios, name="funcionarios"),
    path("funcionarios/novo/", views.funcionario_novo, name="funcionario_novo"),
    path("funcionarios/<int:pk>/", views.funcionario_editar, name="funcionario_editar"),
    path(
        "funcionarios/<int:pk>/redefinir-senha/",
        views.funcionario_redefinir_senha,
        name="funcionario_redefinir_senha",
    ),
    path(
        "funcionarios/<int:pk>/zerar-2fa/",
        views.funcionario_zerar_2fa,
        name="funcionario_zerar_2fa",
    ),
    path(
        "funcionarios/<int:pk>/desativar/",
        views.funcionario_desativar,
        name="funcionario_desativar",
    ),
]
