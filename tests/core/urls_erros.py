from django.core.exceptions import PermissionDenied
from django.urls import path

from config import urls as urls_do_projeto


def _negar(request):
    raise PermissionDenied


def _quebrar(request):
    raise RuntimeError("erro de teste")


urlpatterns = [
    *urls_do_projeto.urlpatterns,
    path("teste/403/", _negar),
    path("teste/500/", _quebrar),
]

handler403 = urls_do_projeto.handler403
handler404 = urls_do_projeto.handler404
handler500 = urls_do_projeto.handler500
