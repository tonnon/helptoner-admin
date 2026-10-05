from functools import wraps

from django.core.exceptions import PermissionDenied


def eh_administrador(usuario) -> bool:
    return bool(usuario.is_authenticated and usuario.eh_administrador)


def exigir_administrador(usuario) -> None:
    if not eh_administrador(usuario):
        raise PermissionDenied


def requer_administrador(view):
    @wraps(view)
    def envolvida(request, *args, **kwargs):
        exigir_administrador(request.user)
        return view(request, *args, **kwargs)

    return envolvida
