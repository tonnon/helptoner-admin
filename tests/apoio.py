import os
import subprocess
import sys
import uuid
from pathlib import Path

from django.contrib.auth.models import Group

from apps.contas.models import VENDEDOR, Usuario

RAIZ = Path(__file__).resolve().parent.parent


def rodar_django(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Roda o manage.py com o Python atual, em outro processo, e captura a saída como texto."""
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=RAIZ,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


SENHA_TESTE = "senha-de-teste-bem-longa"


def criar_usuario(
    perfil: str = VENDEDOR,
    *,
    email: str | None = None,
    nome: str = "Carla Souza",
    pronto: bool = True,
    senha: str = SENHA_TESTE,
):
    """Cria um usuário no perfil dado. Com `pronto`, ele já trocou a senha e recebeu os códigos."""
    email = email or f"usuario-{uuid.uuid4().hex[:12]}@helptoner.com.br"
    usuario = Usuario.objects.create_user(email, nome, senha)
    usuario.groups.add(Group.objects.get_or_create(name=perfil)[0])
    if pronto:
        usuario.deve_trocar_senha = False
        usuario.codigos_recuperacao_entregues = True
        usuario.save()
    return usuario
