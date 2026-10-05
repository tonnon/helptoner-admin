import itertools
import os
import subprocess
import sys
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path

from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret, hotp_value
from django.contrib.auth.models import Group
from django.db import connection

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


def com_estoque(produto: Produto, quantidade: int, custo: str = "100.00", por=None) -> Produto:
    """Põe `quantidade` no estoque (estoque inicial se não há movimentos, senão entrada)."""
    from apps.contas.models import ADMINISTRADOR
    from apps.estoque.services import registrar_entrada, registrar_estoque_inicial

    por = por or criar_usuario(ADMINISTRADOR)
    if produto.movimentos.exists():
        registrar_entrada(
            produto_id=produto.pk,
            quantidade=quantidade,
            custo_unitario=Decimal(custo),
            observacao="teste",
            usuario=por,
        )
    else:
        registrar_estoque_inicial(
            produto_id=produto.pk,
            quantidade=quantidade,
            custo_unitario=Decimal(custo),
            usuario=por,
        )
    produto.refresh_from_db()
    return produto


def montar_rascunho(usuario, *, cliente=None, itens=(), desconto=None):
    """Monta um rascunho pelos serviços. `itens`: pares (produto, quantidade); `desconto`: par
    (tipo, "valor"). Sem `cliente`, o rascunho fica sem cliente."""
    from apps.pedidos.models import Pedido
    from apps.pedidos.services import (
        adicionar_item,
        criar_rascunho,
        definir_cliente,
        definir_desconto,
    )

    pedido = criar_rascunho(usuario)
    if cliente is not None:
        definir_cliente(pedido.pk, cliente.pk, usuario)
    for produto, quantidade in itens:
        adicionar_item(pedido.pk, produto.pk, quantidade, usuario)
    if desconto is not None:
        tipo, valor = desconto
        definir_desconto(pedido.pk, tipo, Decimal(valor), usuario)
    return Pedido.objects.get(pk=pedido.pk)


def rodar_juntos(*funcoes, espera: float = 30) -> list[object]:
    """Roda cada função numa thread, todas liberadas ao mesmo tempo por uma barreira.

    Devolve, na ordem das funções, o resultado de cada uma ou a exceção que ela levantou.
    Cada thread usa a própria conexão com o banco e a fecha no fim. Se uma thread não chegar à
    barreira ou não terminar em `espera` segundos, o teste falha em vez de ficar parado.
    """
    barreira = threading.Barrier(len(funcoes), timeout=espera)
    resultados: list[object] = [None] * len(funcoes)

    def rodar(indice, funcao):
        try:
            barreira.wait()
            resultados[indice] = funcao()
        except Exception as erro:
            resultados[indice] = erro
        finally:
            connection.close()

    threads = [
        threading.Thread(target=rodar, args=(indice, funcao), daemon=True)
        for indice, funcao in enumerate(funcoes)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(espera)
    paradas = [indice for indice, thread in enumerate(threads) if thread.is_alive()]
    if paradas:
        raise AssertionError(f"As funções {paradas} não terminaram em {espera} s.")
    return resultados
