import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from apps.core.sentry import limpar_evento
from scripts.vercel_build import main

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_VERCEL = {
    "DJANGO_SETTINGS_MODULE": "config.settings.producao",
    "DJANGO_SECRET_KEY": "x" * 60,
    "DATABASE_URL": "postgres://u:p@ep-x-pooler.sa-east-1.aws.neon.tech/db?sslmode=require",
    "VERCEL_URL": "helptoner-abc.vercel.app",
    "VERCEL_PROJECT_PRODUCTION_URL": "helptoner.vercel.app",
    "DJANGO_ALLOWED_HOSTS": "pedidos.helptoner.com.br",
    "SENTRY_DSN": "https://abc@o0.ingest.sentry.io/0",
}
SCRIPT = (
    "import json, django; django.setup(); from django.conf import settings as s; "
    "import sentry_sdk; o = sentry_sdk.get_client().options; d = s.DATABASES['default']; "
    "print(json.dumps({'hosts': s.ALLOWED_HOSTS, 'csrf': s.CSRF_TRUSTED_ORIGINS, "
    "'idade': d['CONN_MAX_AGE'], 'cursores': d['DISABLE_SERVER_SIDE_CURSORS'], "
    "'ssl': d['OPTIONS'].get('sslmode'), "
    "'prepare': d['OPTIONS'].get('prepare_threshold', 'ausente'), "
    "'ip': s.ALLAUTH_TRUSTED_CLIENT_IP_HEADER, 'pii': o['send_default_pii'], "
    "'corpo': o['max_request_body_size'], 'locais': o['include_local_variables'], "
    "'traces': o['traces_sample_rate'], "
    "'armazenamento': s.STORAGES['staticfiles']['BACKEND']}))"
)


def test_configuracao_de_producao():
    r = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        env=os.environ | ENV_VERCEL,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    c = json.loads(r.stdout)
    assert set(c["hosts"]) == {
        "helptoner-abc.vercel.app",
        "helptoner.vercel.app",
        "pedidos.helptoner.com.br",
    }
    assert "https://pedidos.helptoner.com.br" in c["csrf"]
    assert (c["idade"], c["cursores"], c["ssl"], c["prepare"]) == (0, True, "require", None)
    assert c["ip"] == "x-vercel-forwarded-for"
    assert (c["pii"], c["corpo"], c["locais"], c["traces"]) == (False, "never", False, 0.0)
    assert c["armazenamento"] == "whitenoise.storage.CompressedManifestStaticFilesStorage"


def _rodar_python(codigo, env):
    return subprocess.run(
        [sys.executable, "-W", "error::UserWarning", "-c", codigo],
        env=os.environ | env,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
        check=False,
    )


def test_producao_sem_sentry_dsn_sobe_sem_sentry():
    env = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
    env |= {k: v for k, v in ENV_VERCEL.items() if k != "SENTRY_DSN"}
    codigo = "import django, sentry_sdk; django.setup(); print(sentry_sdk.get_client().is_active())"
    r = subprocess.run(
        [sys.executable, "-c", codigo],
        env=env,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"


def test_producao_sem_staticfiles_nao_avisa_do_whitenoise(tmp_path):
    # Executa fora da raiz do projeto não serve: o STATIC_ROOT é BASE_DIR/staticfiles.
    assert not (BASE_DIR / "staticfiles").exists()
    codigo = (
        "import django; django.setup(); "
        "from django.core.wsgi import get_wsgi_application; get_wsgi_application()"
    )
    r = _rodar_python(codigo, ENV_VERCEL)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize(
    ("env", "esperado"),
    [
        ({}, "x-vercel-forwarded-for"),
        ({"CABECALHO_IP_CLIENTE": "x-forwarded-for"}, "x-forwarded-for"),
        ({"CABECALHO_IP_CLIENTE": ""}, None),
    ],
)
def test_cabecalho_do_ip_do_cliente_configuravel(env, esperado):
    codigo = (
        "import django; django.setup(); from django.conf import settings as s; "
        "print(repr(s.ALLAUTH_TRUSTED_CLIENT_IP_HEADER))"
    )
    base = {k: v for k, v in os.environ.items() if k != "CABECALHO_IP_CLIENTE"}
    r = subprocess.run(
        [sys.executable, "-c", codigo],
        env=base | ENV_VERCEL | env,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == repr(esperado)


def test_sentry_tira_dados_do_banco_das_mensagens_de_erro():
    detalhe = "DETAIL:  Key (documento)=(12345678909) already exists."
    texto = f'duplicate key value violates unique constraint "uq"\n{detalhe}'
    evento = {
        "exception": {"values": [{"type": "IntegrityError", "value": texto}]},
        "logentry": {"message": texto, "formatted": texto},
        "message": "falhou Key (documento)=(12345678909) já existe",
    }
    limpo = limpar_evento(evento, {})
    saidas = [
        limpo["exception"]["values"][0]["value"],
        limpo["logentry"]["message"],
        limpo["logentry"]["formatted"],
        limpo["message"],
    ]
    for saida in saidas:
        assert "12345678909" not in saida
        assert "DETAIL" not in saida
    assert "duplicate key value violates" in saidas[0]


def test_sentry_nao_leva_dados_pessoais():
    evento = {
        "user": {"email": "carla@x.com"},
        "request": {
            "url": "https://h/pedidos/?busca=João",
            "method": "GET",
            "cookies": {"sessionid": "x"},
            "headers": {"Cookie": "x"},
            "data": {"nome": "João"},
            "query_string": "busca=João",
            "env": {"REMOTE_ADDR": "1.2.3.4"},
        },
    }
    assert limpar_evento(evento, {}) == {"request": {"url": "https://h/pedidos/", "method": "GET"}}


def test_build_so_migra_na_previa():
    rodar = Mock()
    main({"VERCEL_ENV": "production", "DATABASE_URL": "a"}, rodar)
    rodar.assert_not_called()
    main(
        {"VERCEL_ENV": "preview", "DATABASE_URL": "pooler", "DATABASE_URL_DIRETA": "direta"}, rodar
    )
    args, kwargs = rodar.call_args
    assert args[0][-2:] == ["migrate", "--noinput"]
    assert kwargs["env"]["DATABASE_URL"] == "direta"
    assert kwargs["check"]


def test_build_na_previa_sem_url_direta_usa_a_do_pooler():
    rodar = Mock()
    main({"VERCEL_ENV": "preview", "DATABASE_URL": "pooler"}, rodar)
    assert rodar.call_args.kwargs["env"]["DATABASE_URL"] == "pooler"


def test_caminho_com_quebra_de_linha_sai_escapado_nos_logs(rf, caplog):
    from apps.core.middleware import RecusarNuloMiddleware
    from apps.core.views import erro_403

    # O RequestFactory descarta CR/LF da URL; o caminho é posto à mão, como se viesse de %0d%0a.
    requisicao = rf.get("/a")
    requisicao.path = "/a\r\nFORJADA/"
    nula = rf.get("/x", {"q": "\x00"})
    nula.path = "/x\r\nFORJADA/"
    with caplog.at_level(logging.WARNING):
        erro_403(requisicao)
        RecusarNuloMiddleware(Mock())(nula)
    mensagens = [r.getMessage() for r in caplog.records]
    assert len(mensagens) == 2
    for m in mensagens:
        assert "\n" not in m
        assert "\r" not in m
        assert "\\r\\nFORJADA" in m


def test_erro_500_usa_o_id_do_evento_do_sentry(rf):
    from apps.core.views import erro_500

    with patch("apps.core.views.sentry_sdk.last_event_id", return_value="abc123def456"):
        resposta = erro_500(rf.get("/"))
    assert b"abc123def456" in resposta.content


def test_erro_500_sem_sentry_usa_codigo_local(rf):
    from apps.core.views import erro_500

    with (
        patch("apps.core.views.sentry_sdk.last_event_id", return_value=None),
        patch("apps.core.views.secrets.token_hex", return_value="cafe1234"),
    ):
        resposta = erro_500(rf.get("/"))
    assert resposta.status_code == 500
    assert b"cafe1234" in resposta.content
