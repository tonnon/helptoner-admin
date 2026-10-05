import pytest
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.contas.models import Usuario


def test_email_e_gravado_em_minusculas_e_e_unico(db):
    u = Usuario.objects.create_user(" Carla@HelpToner.com.br ", "Carla", "senha-forte-1234")
    assert u.email == "carla@helptoner.com.br"
    with pytest.raises(IntegrityError):
        Usuario.objects.create_user("CARLA@helptoner.com.br", "Outra", "senha-forte-1234")


def test_migracao_cria_os_dois_perfis(db):
    assert {"Administrador", "Vendedor"} <= set(Group.objects.values_list("name", flat=True))


def test_superusuario_e_administrador(db):
    u = Usuario.objects.create_superuser(
        "lucas@helptoner.com.br", "Lucas Tonnon", "senha-forte-1234"
    )
    assert u.is_staff and u.is_superuser and u.eh_administrador and u.perfil == "Administrador"
    assert u.primeiro_nome == "Lucas"


def test_senhas_usam_argon2():
    from config.settings import base

    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"


@pytest.mark.parametrize(
    "senha,aceita",
    [
        ("curta123456", False),  # 11 caracteres
        ("password1234", False),  # senha comum
        ("123456789012", False),  # só números
        ("carla@helptoner", False),  # parecida com o e-mail
        ("toner-azul-de-março", True),
    ],
)
def test_regras_de_senha(db, senha, aceita):
    u = Usuario(email="carla@helptoner.com.br", nome="Carla Souza")
    if aceita:
        validate_password(senha, u)
    else:
        with pytest.raises(ValidationError):
            validate_password(senha, u)


def test_historico_do_usuario_nao_guarda_senha(db):
    campos = {f.name for f in Usuario.history.model._meta.fields}
    assert "password" not in campos and "last_login" not in campos
