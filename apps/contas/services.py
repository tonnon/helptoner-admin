"""Regras das contas: o primeiro acesso e a gestão de funcionários pelo Administrador."""

import secrets

from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from apps.core.erros import RegraDeNegocio
from apps.core.permissoes import exigir_administrador

from .models import PERFIS, Usuario

# ---------- Primeiro acesso: nova senha → aplicativo autenticador → códigos de recuperação ----

ETAPA_SENHA = 1
ETAPA_AUTENTICADOR = 2
ETAPA_CODIGOS = 3


def tem_autenticador(usuario) -> bool:
    """O usuário tem o aplicativo autenticador (TOTP) ativo."""
    return Authenticator.objects.filter(user=usuario, type=Authenticator.Type.TOTP).exists()


def etapa_do_primeiro_acesso(usuario) -> int | None:
    """A etapa em que o usuário está, ou None se ele já concluiu o primeiro acesso.

    Só consulta o banco quando os códigos de recuperação ainda não foram entregues.
    """
    if usuario.deve_trocar_senha:
        return ETAPA_SENHA
    if usuario.codigos_recuperacao_entregues:
        return None
    return ETAPA_CODIGOS if tem_autenticador(usuario) else ETAPA_AUTENTICADOR


# ---------- Funcionários ----------
# Cada ação grava só os campos que muda (update_fields): assim nunca desfaz uma desativação
# feita ao mesmo tempo por outro administrador (§4.2: o acesso acaba na hora).

ALFABETO_DA_SENHA = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
EMAIL_REPETIDO = "Já existe um funcionário com este e-mail."


def gerar_senha_temporaria() -> str:
    """16 caracteres sorteados, em 4 grupos (ex.: "Kq7m-Xa2c-9pTw-hE4n"), sem 0/O nem 1/l/I."""
    caracteres = "".join(secrets.choice(ALFABETO_DA_SENHA) for _ in range(16))
    return "-".join(caracteres[i : i + 4] for i in range(0, 16, 4))


def _grupo(perfil: str) -> Group:
    if perfil not in PERFIS:
        raise RegraDeNegocio("Perfil inválido.")
    return Group.objects.get_or_create(name=perfil)[0]


def _gravar(usuario: Usuario, *, por, motivo: str | None, campos: list[str] | None = None):
    """Salva com o autor e o motivo que vão para o histórico (simple-history)."""
    usuario._history_user = por
    usuario._change_reason = motivo
    try:
        usuario.save(update_fields=campos)
    finally:  # não deixa autor e motivo para uma gravação seguinte do mesmo objeto
        del usuario._history_user, usuario._change_reason


def criar_funcionario(*, nome: str, email: str, perfil: str, por) -> tuple[Usuario, str]:
    """Cria o funcionário e devolve a senha temporária, que não fica gravada em lugar nenhum.

    No primeiro acesso, ele troca a senha e configura a verificação em duas etapas. Não cria
    EmailAddress do allauth: um endereço não verificado travaria a ativação do autenticador.
    """
    exigir_administrador(por)
    grupo = _grupo(perfil)
    email = email.strip().lower()
    if Usuario.objects.filter(email=email).exists():
        raise RegraDeNegocio(EMAIL_REPETIDO)
    senha = gerar_senha_temporaria()
    usuario = Usuario(email=email, nome=nome.strip(), deve_trocar_senha=True)
    usuario.set_password(senha)
    try:
        with transaction.atomic():
            _gravar(usuario, por=por, motivo="Funcionário criado")
            usuario.groups.add(grupo)
    except IntegrityError:  # o mesmo e-mail cadastrado ao mesmo tempo por outro administrador
        raise RegraDeNegocio(EMAIL_REPETIDO) from None
    return usuario, senha


def alterar_funcionario(usuario: Usuario, *, nome: str, perfil: str, por) -> Usuario:
    """Muda nome e perfil. O Administrador não muda o próprio perfil (P13).

    Nome e perfil ficam em registros de histórico separados: o motivo "Perfil: …" é mostrado
    no lugar das diferenças e esconderia a troca de nome.
    """
    exigir_administrador(por)
    grupo = _grupo(perfil)
    anterior = usuario.perfil
    if perfil != anterior and usuario.pk == por.pk:
        raise RegraDeNegocio("Você não pode mudar o seu próprio perfil.")
    nome = nome.strip()
    with transaction.atomic():
        if nome != usuario.nome:
            usuario.nome = nome
            _gravar(usuario, por=por, motivo=None, campos=["nome"])
        if perfil != anterior:
            usuario.groups.remove(*Group.objects.filter(name__in=PERFIS))
            usuario.groups.add(grupo)
            usuario.__dict__.pop("_nomes_dos_grupos", None)  # o perfil guardado no objeto
            # O grupo não entra no histórico: esta gravação, sem mudar campos, registra a troca.
            _gravar(usuario, por=por, motivo=f"Perfil: {anterior} → {perfil}", campos=["nome"])
    return usuario


def redefinir_senha(usuario: Usuario, *, por) -> str:
    """Gera uma nova senha temporária. A troca da senha encerra as sessões do funcionário."""
    exigir_administrador(por)
    senha = gerar_senha_temporaria()
    usuario.set_password(senha)
    usuario.deve_trocar_senha = True
    _gravar(usuario, por=por, motivo="Senha redefinida", campos=["password", "deve_trocar_senha"])
    return senha


def zerar_2fa(usuario: Usuario, *, por) -> None:
    """Apaga o autenticador e os códigos de recuperação (celular perdido).

    O funcionário volta à etapa 2 do primeiro acesso e configura o aplicativo de novo.
    """
    exigir_administrador(por)
    with transaction.atomic():
        Authenticator.objects.filter(user=usuario).delete()
        usuario.codigos_recuperacao_entregues = False
        _gravar(
            usuario,
            por=por,
            motivo="Verificação em duas etapas zerada",
            campos=["codigos_recuperacao_entregues"],
        )


def desativar_funcionario(usuario: Usuario, *, por) -> None:
    """Tira o acesso na hora e mantém o histórico do funcionário.

    O login recusa quem está inativo, e as sessões abertas deixam de valer porque o Django não
    carrega usuário inativo. O Administrador não desativa a si mesmo (P13).
    """
    exigir_administrador(por)
    if usuario.pk == por.pk:
        raise RegraDeNegocio("Você não pode desativar a si mesmo.")
    if not usuario.is_active:
        return
    usuario.is_active = False
    _gravar(usuario, por=por, motivo="Funcionário desativado", campos=["is_active"])
