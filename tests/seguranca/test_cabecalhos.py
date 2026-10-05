from django.core.cache import cache


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
    cache.set("teste", 1)
    assert cache.get("teste") == 1  # a tabela foi criada pela migração
