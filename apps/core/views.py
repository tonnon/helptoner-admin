import logging
import secrets

from django.contrib.auth.decorators import login_not_required
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseServerError,
    JsonResponse,
)
from django.shortcuts import render
from django.template import loader
from django.views.decorators.http import require_GET

from apps.pedidos.consultas import numeros_do_mes, rascunhos_abertos, ultimos_pedidos

from .htmx import eh_htmx

log_seguranca = logging.getLogger("helptoner.seguranca")
log_erros = logging.getLogger("helptoner.erros")


@login_not_required
@require_GET
def saude(request):
    """Página de saúde: não toca em usuário, sessão nem banco."""
    return JsonResponse({"status": "ok"})


def inicio(request):
    """Início (padrão P18): saudação e botão na página; o painel chega por HTMX."""
    if not eh_htmx(request):
        return render(request, "core/inicio.html")
    contexto = {
        "numeros": numeros_do_mes(request.user),
        "rascunhos": rascunhos_abertos(request.user),
        "ultimos": ultimos_pedidos(),
    }
    return render(request, "core/inicio.html#painel", contexto)


@login_not_required
def rota_bloqueada(request, *args, **kwargs):
    """Rota desligada de propósito: responde 404 como se não existisse."""
    raise Http404


def erro_400(request, exception=None):
    # Sem o request, como o erro_500: a página não depende da sessão nem do banco.
    return HttpResponseBadRequest(loader.render_to_string("400.html"))


def erro_403(request, exception=None):
    usuario = getattr(request, "user", None)
    log_seguranca.warning(
        "acesso negado usuario=%s caminho=%s",
        getattr(usuario, "pk", None),
        request.path,
    )
    return render(request, "403.html", status=403)


def erro_404(request, exception=None):
    return render(request, "404.html", status=404)


def erro_500(request):
    codigo = secrets.token_hex(4)
    log_erros.error("erro interno codigo=%s caminho=%s", codigo, request.path, exc_info=True)
    # Sem o request, nenhum context processor roda: a página não depende da sessão nem do
    # banco (que podem ser a causa do erro) e não consome as mensagens da próxima página.
    return HttpResponseServerError(loader.render_to_string("500.html", {"codigo": codigo}))


def falha_csrf(request, reason=""):
    if eh_htmx(request):
        resposta = HttpResponse(status=403)
        resposta["HX-Refresh"] = "true"
        return resposta
    return render(
        request,
        "403.html",
        {"mensagem": "Sua sessão foi renovada. Recarregue a página e tente de novo."},
        status=403,
    )
