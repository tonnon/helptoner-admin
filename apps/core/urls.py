from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("historico/", views.historico, name="historico"),
    path("saude/", views.saude, name="saude"),
]
