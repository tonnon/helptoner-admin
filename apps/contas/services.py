"""Regras das contas: o primeiro acesso e a gestão de funcionários pelo Administrador."""

import secrets

from allauth.mfa.models import Authenticator
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.erros import RegraDeNegocio
from apps.core.permissoes import exigir_administrador

from .models import PERFIS, VENDEDOR, Usuario

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
SEM_PAINEL = " e acesso ao painel removido"


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


def _tirar_o_painel(usuario: Usuario, *, por, motivo: str, campos: list[str]):
    """Ruling R15: um Administrador que não é superusuário e zera o 2FA, redefine a senha ou
    rebaixa um superusuário também tira dele o acesso ao painel de manutenção.

    Senão, ele poderia tomar a conta (2FA zerado e senha temporária na mão), concluir o primeiro
    acesso com o próprio celular e entrar no painel, que é só do superusuário (§4.3). Entre
    superusuários, nada muda. Devolve o motivo e os campos da gravação, já ajustados.
    """
    if por.is_superuser or not usuario.is_superuser:
        return motivo, campos
    usuario.is_superuser = False
    usuario.is_staff = False
    return motivo + SEM_PAINEL, [*campos, "is_superuser", "is_staff"]


def _encerrar_sessoes(usuario: Usuario) -> None:
    """Apaga as sessões abertas do usuário (§4.2: as sessões são invalidadas).

    As sessões ficam no banco (o padrão do Django), sem índice por usuário: cada sessão ainda
    válida é lida. São poucas (poucos funcionários, 2 horas de validade).
    """
    abertas = Session.objects.filter(expire_date__gt=timezone.now()).iterator()
    dele = [s.pk for s in abertas if s.get_decoded().get(SESSION_KEY) == str(usuario.pk)]
    Session.objects.filter(pk__in=dele).delete()


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
            motivo, campos = f"Perfil: {anterior} → {perfil}", ["nome"]
            if perfil == VENDEDOR:
                motivo, campos = _tirar_o_painel(usuario, por=por, motivo=motivo, campos=campos)
            _gravar(usuario, por=por, motivo=motivo, campos=campos)
    return usuario


def redefinir_senha(usuario: Usuario, *, por) -> str:
    """Gera uma nova senha temporária. A troca da senha encerra as sessões do funcionário."""
    exigir_administrador(por)
    senha = gerar_senha_temporaria()
    usuario.set_password(senha)
    usuario.deve_trocar_senha = True
    motivo, campos = _tirar_o_painel(
        usuario, por=por, motivo="Senha redefinida", campos=["password", "deve_trocar_senha"]
    )
    _gravar(usuario, por=por, motivo=motivo, campos=campos)
    return senha


def zerar_2fa(usuario: Usuario, *, por) -> None:
    """Apaga o autenticador e os códigos de recuperação (celular perdido) e encerra as sessões.

    Uma sessão que continuasse aberta no celular perdido seria levada à ativação do autenticador
    e poderia cadastrar outro aplicativo na conta. No próximo acesso, o funcionário entra com a
    senha e volta à etapa 2 do primeiro acesso. Quando o Administrador zera o próprio 2FA, as
    sessões dele também acabam, inclusive a atual (o celular perdido pode ser o dele): a view o
    leva ao login.
    """
    exigir_administrador(por)
    with transaction.atomic():
        Authenticator.objects.filter(user=usuario).delete()
        usuario.codigos_recuperacao_entregues = False
        motivo, campos = _tirar_o_painel(
            usuario,
            por=por,
            motivo="Verificação em duas etapas zerada",
            campos=["codigos_recuperacao_entregues"],
        )
        _gravar(usuario, por=por, motivo=motivo, campos=campos)
        _encerrar_sessoes(usuario)


def desativar_funcionario(usuario: Usuario, *, por) -> None:
    """Tira o acesso na hora e mantém o histórico do funcionário.

    O login recusa quem está inativo, e as sessões abertas são apagadas (uma reativação pelo
    painel não as traz de volta). O Administrador não desativa a si mesmo (P13).
    """
    exigir_administrador(por)
    if usuario.pk == por.pk:
        raise RegraDeNegocio("Você não pode desativar a si mesmo.")
    if not usuario.is_active:
        return
    with transaction.atomic():
        usuario.is_active = False
        _gravar(usuario, por=por, motivo="Funcionário desativado", campos=["is_active"])
        _encerrar_sessoes(usuario)
