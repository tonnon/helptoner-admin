from django.test import Client, override_settings


@override_settings(ROOT_URLCONF="tests.core.urls_erros")
def test_403_no_visual_do_sistema_e_registrado(client_vendedor, caplog):
    r = client_vendedor.get("/teste/403/")
    assert r.status_code == 403 and "Voltar ao início" in r.content.decode()
    assert any("acesso negado" in m and "/teste/403/" in m for m in caplog.messages)


@override_settings(ROOT_URLCONF="tests.core.urls_erros")
def test_500_mostra_codigo_de_referencia(client_vendedor):
    client_vendedor.raise_request_exception = False
    r = client_vendedor.get("/teste/500/")
    assert r.status_code == 500 and "Código de referência:" in r.content.decode()


def test_404_no_visual_do_sistema(client_vendedor):
    r = client_vendedor.get("/nao-existe/")
    assert r.status_code == 404 and "Página não encontrada" in r.content.decode()


def test_falha_de_csrf_no_htmx_recarrega_a_pagina(vendedor):
    c = Client(enforce_csrf_checks=True)
    c.force_login(vendedor)
    r = c.post("/", headers={"HX-Request": "true"})
    assert r.status_code == 403 and r["HX-Refresh"] == "true"
