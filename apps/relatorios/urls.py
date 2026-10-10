from django.urls import path

from . import views

app_name = "relatorios"

urlpatterns = [
    path("relatorios/", views.relatorio, name="resumo"),
    path("relatorios/<slug:aba>/", views.relatorio, name="aba"),
]
