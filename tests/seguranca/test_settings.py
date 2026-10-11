from tests.apoio import rodar_django


def test_local_recusa_rodar_na_vercel():
    env = {"DJANGO_SETTINGS_MODULE": "config.settings.local", "VERCEL": "1"}
    r = rodar_django("check", env=env)
    assert r.returncode != 0 and "config.settings.local" in r.stderr


def test_producao_exige_chave_secreta():
    r = rodar_django(
        "check",
        env={
            "DJANGO_SETTINGS_MODULE": "config.settings.producao",
            "DJANGO_SECRET_KEY": "",
            "DATABASE_URL": "postgres://u:p@localhost/x",
        },
    )
    assert r.returncode != 0 and "DJANGO_SECRET_KEY" in r.stderr


def test_banco_de_teste_e_postgresql_18(db):
    from django.db import connection

    assert connection.vendor == "postgresql" and connection.pg_version >= 180000
