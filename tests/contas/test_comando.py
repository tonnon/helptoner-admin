import re
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.contas.models import Usuario


def test_criar_primeiro_admin(db):
    saida = StringIO()
    call_command(
        "criar_primeiro_admin", email="lucas@helptoner.com.br", nome="Lucas Tonnon", stdout=saida
    )
    u = Usuario.objects.get()
    assert u.is_superuser and u.is_staff and u.eh_administrador and u.deve_trocar_senha
    senha = re.search(r"Senha temporária: (\S+)", saida.getvalue()).group(1)
    assert u.check_password(senha)
    with pytest.raises(CommandError, match="Já existe"):
        call_command(
            "criar_primeiro_admin", email="lucas@helptoner.com.br", nome="Lucas", stdout=StringIO()
        )


def test_criar_primeiro_admin_confere_os_dados(db):
    with pytest.raises(CommandError, match="E-mail inválido"):
        call_command("criar_primeiro_admin", email="lucas", nome="Lucas", stdout=StringIO())
    with pytest.raises(CommandError, match="Informe o nome"):
        call_command(
            "criar_primeiro_admin", email="lucas@helptoner.com.br", nome="  ", stdout=StringIO()
        )
    assert not Usuario.objects.exists()


def test_email_do_primeiro_admin_em_minusculas(db):
    call_command(
        "criar_primeiro_admin", email=" Lucas@Helptoner.com.br ", nome="Lucas", stdout=StringIO()
    )
    assert Usuario.objects.get().email == "lucas@helptoner.com.br"
    with pytest.raises(CommandError, match="Já existe"):
        call_command(
            "criar_primeiro_admin", email="LUCAS@helptoner.com.br", nome="Lucas", stdout=StringIO()
        )
