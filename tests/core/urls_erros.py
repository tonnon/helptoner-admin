from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.urls import path

from config import urls as urls_do_projeto


def _suspeitar(request):
    raise SuspiciousOperation("requisição de teste")


def _negar(request):
    raise PermissionDenied


def _quebrar(request):
    raise RuntimeError("erro de teste")


urlpatterns = [
    *urls_do_projeto.urlpatterns,
    path("teste/400/", _suspeitar),
    path("teste/403/", _negar),
    path("teste/500/", _quebrar),
]

handler400 = urls_do_projeto.handler400
handler403 = urls_do_projeto.handler403
handler404 = urls_do_projeto.handler404
handler500 = urls_do_projeto.handler500
