from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.http import QueryDict
from django.middleware.clickjacking import XFrameOptionsMiddleware
from django.middleware.csp import ContentSecurityPolicyMiddleware
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

from .htmx import eh_htmx, redirecionar
from .views import erro_400, log_seguranca

_NULO = "\x00"


def _tem_nulo(dados: QueryDict) -> bool:
    return any(
        _NULO in chave or any(_NULO in valor for valor in valores)
        for chave, valores in dados.lists()
    )


class RecusarNuloMiddleware:
    """Recusa com 400 a requisição com o caractere nulo numa chave ou num valor do GET ou do
    formulário enviado por POST (Ruling R25).

    O PostgreSQL não aceita texto com o caractere nulo: qualquer filtro ou campo que o levasse ao
    banco daria erro 500. Fica logo depois do SecurityMiddleware e responde sem sessão e sem
    banco. Corpo que não é formulário (ex.: JSON) não entra em request.POST e passa direto.
    Ler request.POST aqui impede uma view de trocar os upload handlers; o sistema não recebe
    arquivos.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # A recusa sai antes dos middlewares de baixo: os cabeçalhos que eles poriam (CSP e
        # X-Frame-Options) entram por aqui, iguais aos das outras páginas.
        self.cabecalhos = [
            ContentSecurityPolicyMiddleware(get_response),
            XFrameOptionsMiddleware(get_response),
        ]

    def __call__(self, request):
        if _tem_nulo(request.GET) or _tem_nulo(request.POST):
            log_seguranca.warning("caractere nulo recusado caminho=%r", request.path)
            resposta = erro_400(request)
            for middleware in self.cabecalhos:
                resposta = middleware.process_response(request, resposta)
            return resposta
        return self.get_response(request)


class LoginObrigatorioMiddleware(LoginRequiredMiddleware):
    """Exige login em todas as views; em HTMX, manda o navegador inteiro para o login."""

    def get_login_url(self, view_func):
        # Um login só, o do sistema (com a verificação em duas etapas). As views do painel do
        # Django trazem login_url próprio (admin:login), que entraria sem o código: é ignorado.
        return settings.LOGIN_URL

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
