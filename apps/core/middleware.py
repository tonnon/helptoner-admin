from urllib.parse import urlsplit

from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.http import QueryDict
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

from .htmx import eh_htmx, redirecionar


class LoginObrigatorioMiddleware(LoginRequiredMiddleware):
    """Exige login em todas as views; em HTMX, manda o navegador inteiro para o login."""

    def handle_no_permission(self, request, view_func):
        if not eh_htmx(request):
            return super().handle_no_permission(request, view_func)
        atual = request.headers.get("HX-Current-URL", "")
        proximo = "/"
        if atual and url_has_allowed_host_and_scheme(atual, allowed_hosts={request.get_host()}):
            partes = urlsplit(atual)
            proximo = partes.path + (f"?{partes.query}" if partes.query else "")
        url_login = resolve_url(self.get_login_url(view_func))
        consulta = QueryDict(mutable=True)
        consulta["next"] = proximo
        return redirecionar(request, f"{url_login}?{consulta.urlencode(safe='/')}")
