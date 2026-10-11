import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse

from apps.core.permissoes import eh_administrador, exigir_administrador, requer_administrador


def test_requer_administrador(rf, administrador, vendedor):
    view = requer_administrador(lambda request: HttpResponse("ok"))
    req = rf.get("/")
    req.user = vendedor
    with pytest.raises(PermissionDenied):
        view(req)
    req.user = administrador
    assert view(req).status_code == 200
    assert eh_administrador(AnonymousUser()) is False


def test_exigir_administrador(administrador, vendedor):
    exigir_administrador(administrador)
    with pytest.raises(PermissionDenied):
        exigir_administrador(vendedor)
