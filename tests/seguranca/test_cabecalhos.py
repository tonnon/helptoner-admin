import pytest
from django.core.cache import cache
from django.utils.cache import has_vary_header

from apps.contas.models import Usuario
from tests.apoio import SENHA_TESTE, criar_usuario, totp_agora

HTMX = {"HX-Request": "true"}


def test_cabecalhos_de_seguranca(client):
    r = client.get("/saude/")
    csp = r["Content-Security-Policy"]
    for trecho in [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "form-action 'self'",
    ]:
        assert trecho in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r["X-Frame-Options"] == "DENY" and r["X-Content-Type-Options"] == "nosniff"
    assert r["Referrer-Policy"] == "same-origin"
    assert r["Cross-Origin-Opener-Policy"] == "same-origin"


def test_sessao_expira_em_2_horas_sem_uso(settings):
    assert settings.SESSION_COOKIE_AGE == 7200 and settings.SESSION_SAVE_EVERY_REQUEST
    assert settings.SESSION_COOKIE_HTTPONLY and settings.SESSION_COOKIE_SAMESITE == "Lax"


def test_cache_fica_no_postgresql(db, settings):
    assert settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
    # Revisão final (M6): com o limite padrão (300 linhas), uma enxurrada de logins errados
    # tiraria do cache os contadores de tentativas, inclusive o bloqueio por conta.
    assert settings.CACHES["default"]["OPTIONS"] == {"MAX_ENTRIES": 10000}
    cache.set("teste", 1)
    assert cache.get("teste") == 1  # a tabela foi criada pela migração


# Revisão final (I2): a página e o pedaço HTMX das listas têm a mesma URL. Sem "Vary: HX-Request",
# o botão Voltar do navegador pode mostrar, do cache, só o pedaço (sem menu e sem estilo).
@pytest.mark.parametrize("cabecalhos", [{}, HTMX], ids=["pagina", "htmx"])
@pytest.mark.parametrize("url", ["/", "/pedidos/", "/clientes/"])
def test_respostas_variam_conforme_o_htmx(client_vendedor, url, cabecalhos):
    r = client_vendedor.get(url, headers=cabecalhos)
    assert r.status_code == 200 and has_vary_header(r, "HX-Request")


@pytest.mark.parametrize("cabecalhos", [{}, HTMX], ids=["pagina", "htmx"])
def test_ida_ao_login_tambem_varia_conforme_o_htmx(client, db, cabecalhos):
    # Sem login, a página recebe 302 e o HTMX recebe HX-Redirect, na mesma URL.
    assert has_vary_header(client.get("/pedidos/", headers=cabecalhos), "HX-Request")


# Revisão final (M7): as telas que mostram o segredo do autenticador e os códigos de recuperação
# não ficam no cache do navegador (como a da senha temporária).
def test_telas_que_mostram_segredos_nao_ficam_em_cache(client, db):
    u = criar_usuario(pronto=False)
    Usuario.objects.filter(pk=u.pk).update(deve_trocar_senha=False)
    client.post("/contas/login/", {"login": u.email, "password": SENHA_TESTE})
    r = client.get("/contas/2fa/totp/activate/")
    assert r.status_code == 200 and "no-store" in r["Cache-Control"]
    client.post("/contas/2fa/totp/activate/", {"code": totp_agora(r.context["form"].secret)})
    r = client.get("/contas/2fa/recovery-codes/")
    assert r.status_code == 200 and "no-store" in r["Cache-Control"]
    assert "no-store" not in client.get("/minha-conta/").get("Cache-Control", "")
