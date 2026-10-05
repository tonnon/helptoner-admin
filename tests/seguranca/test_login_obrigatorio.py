import re
from urllib.parse import parse_qs, urlparse

from django.urls import URLPattern, URLResolver, get_resolver

# Rotas do allauth desligadas em config/urls.py: respondem 404 para todos, com ou sem login.
ROTAS_DESLIGADAS = {
    "account_signup",
    "account_email",
    "account_email_verification_sent",
    "account_confirm_email",
    "account_set_password",
    "account_reset_password",
    "account_reset_password_done",
    "account_reset_password_from_key",
    "account_reset_password_from_key_done",
    "account_confirm_login_code",
    "mfa_deactivate_totp",
}

# Cada tarefa que criar rota sem login acrescenta aqui, com o motivo.
ROTAS_LIVRES = {
    "core:saude",  # monitoramento: não toca em usuário, sessão nem banco
    "account_login",  # a tela de login
    "mfa_authenticate",  # segunda etapa do login: a pessoa ainda não entrou
    "account_inactive",  # aviso para quem tentou entrar com um acesso desativado
    *ROTAS_DESLIGADAS,
}


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
    """Pares (nome, url): <int:...> vira "1" e os outros conversores viram "x".

    Nas rotas com expressão regular (as do allauth), cada grupo (?P<nome>...) vira "x" e as
    âncoras ^ e $ saem.
    """
    rotas = []
    for nome, rota, _ in _percorrer(get_resolver().url_patterns):
        url = re.sub(r"<int:[^>]+>", "1", rota)
        url = re.sub(r"<[^>]+>", "x", url)
        url = re.sub(r"\(\?Px[^)]*\)", "x", url).replace("^", "").replace("$", "")
        assert not re.search(r"[\^$()?\[\]]", url), f"rota {nome} não se deixa montar: {rota}"
        rotas.append((nome, "/" + url))
    return rotas


def test_toda_rota_exige_login(client, db):
    for nome, url in todas_as_rotas():
        if nome in ROTAS_LIVRES:
            continue
        r = client.get(url)
        assert r.status_code == 302 and r["Location"].startswith("/contas/login/"), nome


def test_rotas_desligadas_respondem_404_mesmo_com_login(client_vendedor):
    desligadas = [(nome, url) for nome, url in todas_as_rotas() if nome in ROTAS_DESLIGADAS]
    assert {nome for nome, _ in desligadas} == ROTAS_DESLIGADAS
    for nome, url in desligadas:
        assert client_vendedor.get(url).status_code == 404, nome


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
