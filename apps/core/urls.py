from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("saude/", views.saude, name="saude"),
]
