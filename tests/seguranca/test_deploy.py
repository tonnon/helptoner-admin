import secrets

from tests.apoio import rodar_django

ENV_PRODUCAO_FALSA = {
    "DJANGO_SETTINGS_MODULE": "config.settings.producao",
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
    "DATABASE_URL": "postgres://u:p@localhost:5432/x",
    "DJANGO_ALLOWED_HOSTS": "pedidos.exemplo.com.br",
}


def test_check_deploy_sem_alertas():
    r = rodar_django("check", "--deploy", "--fail-level", "WARNING", env=ENV_PRODUCAO_FALSA)
    assert r.returncode == 0, r.stdout + r.stderr
