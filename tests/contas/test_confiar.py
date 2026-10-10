"""Login com "confiar neste computador" por 30 dias (o 2FA continua obrigatório)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from allauth.mfa.models import Authenticator
from django.conf import settings

from apps.contas import services
from apps.contas.models import RegistroAcesso
from tests.apoio import codigo_totp, criar_usuario
from tests.contas.test_login import codigo_de_recuperacao, entrar_com_senha

COOKIE = "mfa_trusted"
CONFIAR = "/contas/2fa/trust/"
DIAS_30 = 30 * 24 * 3600


def entrar_ate_a_pergunta(client, usuario, **kw):
    """Senha e código; devolve a resposta (a pergunta sobre confiar no computador)."""
    entrar_com_senha(client, usuario.email)
    return client.post("/contas/2fa/authenticate/", {"code": codigo_totp(usuario, **kw)})


def confiar(client, usuario):
    r = entrar_ate_a_pergunta(client, usuario)
    assert r["Location"] == CONFIAR
    r = client.post(CONFIAR, {"action": "trust"})
    assert r.status_code == 302 and r["Location"] == "/"
    return r


def test_depois_do_codigo_aparece_a_pergunta_e_confiar_grava_o_cookie(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    r = entrar_ate_a_pergunta(client, u)
    assert r.status_code == 302 and r["Location"] == CONFIAR
    r = client.get(CONFIAR)
    html = r.content.decode()
    assert "Confiar neste computador?" in html
    assert "daqui a 30 dias" in html
    assert "Agora não" in html
    r = client.post(CONFIAR, {"action": "trust"})
    assert r.status_code == 302 and r["Location"] == "/"
    cookie = r.cookies[COOKIE]
    assert cookie["max-age"] == DIAS_30
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    assert client.get("/").status_code == 200


def test_computador_de_confianca_pula_o_codigo_e_o_login_fica_registrado(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    confiar(client, u)
    client.post("/contas/logout/")
    assert client.get("/").status_code == 302
    r = entrar_com_senha(client, u.email)
    assert r.status_code == 302 and r["Location"] == "/"
    assert client.get("/").status_code == 200
    assert RegistroAcesso.objects.filter(usuario=u, sucesso=True).count() == 2


def test_senha_errada_no_computador_de_confianca_continua_recusada(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    confiar(client, u)
    client.post("/contas/logout/")
    r = entrar_com_senha(client, u.email, "senha-errada-de-novo")
    assert r.status_code == 200
    assert client.get("/").status_code == 302
    assert RegistroAcesso.objects.filter(sucesso=False, email_tentado=u.email).count() == 1


def test_agora_nao_nao_grava_cookie_e_o_proximo_login_pede_o_codigo(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    r = entrar_ate_a_pergunta(client, u)
    assert r["Location"] == CONFIAR
    r = client.post(CONFIAR, {"action": "skip"})
    assert r.status_code == 302 and r["Location"] == "/"
    assert COOKIE not in r.cookies and COOKIE not in client.cookies
    assert client.get("/").status_code == 200
    client.post("/contas/logout/")
    r = entrar_com_senha(client, u.email)
    assert r["Location"] == "/contas/2fa/authenticate/"
    assert client.get("/").status_code == 302


def test_codigo_de_recuperacao_tambem_leva_a_pergunta(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    entrar_com_senha(client, u.email)
    r = client.post("/contas/2fa/authenticate/", {"code": codigo_de_recuperacao(u)})
    assert r.status_code == 302 and r["Location"] == CONFIAR


def test_a_pergunta_exige_ter_passado_pela_senha(client, db):
    criar_usuario(email="carla@helptoner.com.br")
    r = client.get(CONFIAR)
    assert r.status_code == 302 and r["Location"] == "/contas/login/"
    assert COOKIE not in client.post(CONFIAR, {"action": "trust"}).cookies


def test_redefinir_senha_cancela_a_confianca(client, db, administrador):
    u = criar_usuario(email="carla@helptoner.com.br")
    confiar(client, u)
    client.post("/contas/logout/")
    nova = services.redefinir_senha(u, por=administrador)
    r = entrar_com_senha(client, u.email, nova)
    assert r.status_code == 302 and r["Location"] != "/"
    assert client.get("/").status_code == 302


def test_trocar_a_propria_senha_cancela_a_confianca(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    confiar(client, u)
    client.post("/contas/logout/")
    u.refresh_from_db()
    u.set_password("outra-senha-bem-longa-9")
    u.save()
    r = entrar_com_senha(client, u.email, "outra-senha-bem-longa-9")
    assert r["Location"] == "/contas/2fa/authenticate/"


def test_zerar_2fa_cancela_a_confianca_e_pede_configurar_de_novo(client, db, administrador):
    u = criar_usuario(email="carla@helptoner.com.br")
    confiar(client, u)
    client.post("/contas/logout/")
    services.zerar_2fa(u, por=administrador)
    r = entrar_com_senha(client, u.email)
    # Sem autenticador não há código a pedir: entra só com a senha e o sistema leva à ativação
    # do 2FA (primeiro acesso), sem deixar usar nada antes.
    assert r["Location"] != "/contas/2fa/authenticate/"
    assert not Authenticator.objects.filter(user=u).exists()
    assert client.get("/")["Location"] == "/contas/2fa/totp/activate/"
    assert COOKIE in client.cookies  # o cookie antigo segue no navegador, mas não vale mais


def test_depois_de_31_dias_o_codigo_e_pedido_de_novo(client, db, monkeypatch):
    u = criar_usuario(email="carla@helptoner.com.br")
    confiar(client, u)
    client.post("/contas/logout/")
    real = time.time
    # 29 dias: ainda vale.
    monkeypatch.setattr(time, "time", lambda: real() + 29 * 24 * 3600)
    r = entrar_com_senha(client, u.email)
    assert r["Location"] == "/"
    client.post("/contas/logout/")
    # 31 dias: o allauth confere a idade do cookie com time.time.
    monkeypatch.setattr(time, "time", lambda: real() + 31 * 24 * 3600)
    r = entrar_com_senha(client, u.email)
    assert r["Location"] == "/contas/2fa/authenticate/"


def test_cookie_de_producao_e_seguro_httponly_e_lax():
    script = (
        "import json, django; django.setup(); from allauth.mfa import app_settings as a; "
        "print(json.dumps([a.TRUST_ENABLED, a.TRUST_COOKIE_AGE.days, a.TRUST_COOKIE_SECURE, "
        "a.TRUST_COOKIE_HTTPONLY, a.TRUST_COOKIE_SAMESITE]))"
    )
    env = os.environ | {
        "DJANGO_SETTINGS_MODULE": "config.settings.producao",
        "DJANGO_SECRET_KEY": "x" * 60,
        "DATABASE_URL": "postgres://u:p@ep-x-pooler.sa-east-1.aws.neon.tech/db?sslmode=require",
        "VERCEL_URL": "helptoner-abc.vercel.app",
        "VERCEL_PROJECT_PRODUCTION_URL": "helptoner.vercel.app",
        "DJANGO_ALLOWED_HOSTS": "pedidos.helptoner.com.br",
    }
    r = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        cwd=Path(settings.BASE_DIR),
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [True, 30, True, True, "Lax"]
