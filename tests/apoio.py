import itertools
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret, hotp_value
from django.contrib.auth.models import Group

from apps.cadastros.documentos import digitos_verificadores_cnpj, digitos_verificadores_cpf
from apps.cadastros.models import Cliente, Produto
from apps.contas.models import VENDEDOR, Usuario

RAIZ = Path(__file__).resolve().parent.parent

UA_CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


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
    """Cria um usuário no perfil dado.

    Com `pronto`, ele já trocou a senha, ativou o autenticador (TOTP) e recebeu os códigos de
    recuperação.
    """
    email = email or f"usuario-{uuid.uuid4().hex[:12]}@helptoner.com.br"
    usuario = Usuario.objects.create_user(email, nome, senha)
    usuario.groups.add(Group.objects.get_or_create(name=perfil)[0])
    if pronto:
        usuario.deve_trocar_senha = False
        usuario.codigos_recuperacao_entregues = True
        usuario.save()
        ativar_2fa(usuario)
    return usuario


# As funções abaixo usam APIs internas do allauth, que só podem aparecer nos testes.


def ativar_2fa(usuario) -> str:
    """Ativa o TOTP e os códigos de recuperação do usuário e devolve o segredo do TOTP."""
    segredo = generate_totp_secret()
    TOTP.activate(usuario, segredo)
    RecoveryCodes.activate(usuario)
    return segredo


def totp_agora(segredo: str) -> str:
    """O código de 6 dígitos do momento. O allauth recusa o mesmo código duas vezes em 30 s."""
    return f"{hotp_value(segredo, int(time.time()) // 30):06d}"


def codigo_totp(usuario) -> str:
    """O código de 6 dígitos do momento para o TOTP já ativo do usuário."""
    totp = Authenticator.objects.get(user=usuario, type=Authenticator.Type.TOTP)
    return totp_agora(get_mfa_adapter().decrypt(totp.data["secret"]))


_proximo_documento = itertools.count(1)


def criar_cliente(
    nome: str = "Papelaria Central Ltda", *, tipo: str = "PJ", documento=None, **campos
):
    """Cria um cliente. Sem `documento`, gera um CPF ou CNPJ válido e único."""
    if documento is None:
        n = next(_proximo_documento)
        if tipo == "PF":
            base = f"{n:09d}"
            documento = base + digitos_verificadores_cpf(base)
        else:
            base = f"{n:012d}"
            documento = base + digitos_verificadores_cnpj(base)
    return Cliente.objects.create(nome=nome, tipo=tipo, documento=documento, **campos)


def criar_produto(
    codigo: str = "CE285A",
    *,
    descricao: str = "Toner HP 85A Preto",
    marca: str = "HP",
    preco: str = "189.90",
    ativo: bool = True,
) -> Produto:
    """Cria um produto com estoque 0 e custo médio 0 (esses dois só mudam por movimento)."""
    return Produto.objects.create(
        codigo=codigo, descricao=descricao, marca=marca, preco=preco, ativo=ativo
    )
