import re
from urllib.parse import parse_qs, urlparse

from django.urls import URLPattern, URLResolver, get_resolver

ROTAS_LIVRES = {"core:saude"}  # cada tarefa que criar rota sem login acrescenta aqui, com o motivo


def _percorrer(padroes, prefixo_nome="", prefixo_rota=""):
    for p in padroes:
        if isinstance(p, URLResolver):
            ns = f"{prefixo_nome}{p.namespace}:" if p.namespace else prefixo_nome
            yield from _percorrer(p.url_patterns, ns, prefixo_rota + str(p.pattern))
        elif isinstance(p, URLPattern) and p.name:
            yield f"{prefixo_nome}{p.name}", prefixo_rota + str(p.pattern), p.callback


def views_por_nome():
    return [(nome, view) for nome, _, view in _percorrer(get_resolver().url_patterns)]


def todas_as_rotas():
    """Pares (nome, url): <int:...> vira "1" e os outros conversores viram "x"."""
    rotas = []
    for nome, rota, _ in _percorrer(get_resolver().url_patterns):
        url = re.sub(r"<int:[^>]+>", "1", rota)
        url = re.sub(r"<[^>]+>", "x", url)
        assert not re.search(r"[\^$()?\[\]]", url), f"rota {nome} não se deixa montar: {rota}"
        rotas.append((nome, "/" + url))
    return rotas


def test_toda_rota_exige_login(client, db):
    for nome, url in todas_as_rotas():
        if nome in ROTAS_LIVRES:
            continue
        r = client.get(url)
        assert r.status_code == 302 and r["Location"].startswith("/contas/login/"), nome


def test_so_as_rotas_livres_dispensam_login():
    livres = {nome for nome, view in views_por_nome() if not getattr(view, "login_required", True)}
    assert livres <= ROTAS_LIVRES


def test_htmx_sem_sessao_manda_o_navegador_inteiro_para_o_login(client, db):
    r = client.get(
        "/",
        headers={
            "HX-Request": "true",
            "HX-Current-URL": "http://testserver/pedidos/7/editar/?aba=itens",
        },
    )
    destino = urlparse(r["HX-Redirect"])
    assert r.status_code == 200 and destino.path == "/contas/login/"
    assert parse_qs(destino.query)["next"] == ["/pedidos/7/editar/?aba=itens"]


def test_htmx_com_url_de_outro_site_volta_para_o_inicio(client, db):
    r = client.get("/", headers={"HX-Request": "true", "HX-Current-URL": "https://malicioso.com/x"})
    assert parse_qs(urlparse(r["HX-Redirect"]).query)["next"] == ["/"]
