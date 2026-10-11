import json

from django.http import HttpResponse, HttpResponseRedirect


def eh_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def redirecionar(request, url: str) -> HttpResponse:
    """Redireciona o navegador inteiro: HX-Redirect para HTMX, 302 para o resto."""
    if eh_htmx(request):
        resposta = HttpResponse()
        resposta["HX-Redirect"] = url
        return resposta
    return HttpResponseRedirect(url)


def avisar(resposta: HttpResponse, texto: str, tipo: str = "sucesso") -> HttpResponse:
    """Pede ao navegador que mostre um aviso (evento HX-Trigger `aviso`)."""
    resposta["HX-Trigger"] = json.dumps({"aviso": {"texto": texto, "tipo": tipo}})
    return resposta
