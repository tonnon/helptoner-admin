import re

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.test import Client

from apps.contas.models import ADMINISTRADOR, VENDEDOR, Usuario
from apps.contas.services import (
    alterar_funcionario,
    criar_funcionario,
    desativar_funcionario,
    gerar_senha_temporaria,
    redefinir_senha,
    zerar_2fa,
)
from apps.core.erros import RegraDeNegocio
from tests.apoio import criar_usuario

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
SEM_PAINEL = " e acesso ao painel removido"


def _superusuario(email="su@helptoner.com.br", nome="Lucas Super"):
    su = criar_usuario(ADMINISTRADOR, email=email, nome=nome)
    Usuario.objects.filter(pk=su.pk).update(is_staff=True, is_superuser=True)
    return Usuario.objects.get(pk=su.pk)


def _sessoes_de(usuario) -> list[Session]:
    pk = str(usuario.pk)
    return [s for s in Session.objects.all() if s.get_decoded().get("_auth_user_id") == pk]


def test_senha_temporaria_tem_16_caracteres_em_4_grupos():
    senha = gerar_senha_temporaria()
    grupo = f"[{ALFABETO}]{{4}}"
    assert re.fullmatch(f"{grupo}-{grupo}-{grupo}-{grupo}", senha)
    assert len({gerar_senha_temporaria() for _ in range(20)}) == 20


def test_criar_funcionario_gera_senha_temporaria(administrador):
    u, senha = criar_funcionario(
        nome="Ana Lima", email="Ana@Helptoner.com.br", perfil=VENDEDOR, por=administrador
    )
    assert u.email == "ana@helptoner.com.br" and u.perfil == "Vendedor" and u.deve_trocar_senha
    assert len(senha.replace("-", "")) == 16 and u.check_password(senha)
    assert u.history.first().history_change_reason == "Funcionário criado"
    assert u.history.first().history_user == administrador


def test_criar_funcionario_no_perfil_administrador(administrador):
    u, _ = criar_funcionario(
        nome="José Tonnon", email="jose@helptoner.com.br", perfil=ADMINISTRADOR, por=administrador
    )
    u = Usuario.objects.get(pk=u.pk)
    assert u.eh_administrador and list(u.groups.values_list("name", flat=True)) == [ADMINISTRADOR]
    assert not u.is_staff and not u.is_superuser and not u.codigos_recuperacao_entregues


def test_criar_funcionario_nao_cria_endereco_de_email_do_allauth(administrador):
    # Um EmailAddress não verificado faria a ativação do autenticador (allauth) voltar para a
    # tela do 2FA, e o PrimeiroAcessoMiddleware de volta para a ativação: um laço (Ruling R12).
    criar_funcionario(
        nome="Ana Lima", email="ana@helptoner.com.br", perfil=VENDEDOR, por=administrador
    )
    assert not EmailAddress.objects.exists()


def test_so_administrador_gerencia_funcionarios(vendedor):
    with pytest.raises(PermissionDenied):
        criar_funcionario(nome="X", email="x@x.com", perfil=VENDEDOR, por=vendedor)


@pytest.mark.parametrize(
    "acao",
    [
        lambda u, por: alterar_funcionario(u, nome="Outro", perfil=VENDEDOR, por=por),
        lambda u, por: redefinir_senha(u, por=por),
        lambda u, por: zerar_2fa(u, por=por),
        lambda u, por: desativar_funcionario(u, por=por),
    ],
    ids=["alterar", "redefinir_senha", "zerar_2fa", "desativar"],
)
def test_vendedor_nao_mexe_em_funcionario(administrador, vendedor, acao):
    with pytest.raises(PermissionDenied):
        acao(administrador, vendedor)
    administrador.refresh_from_db()
    assert administrador.is_active and administrador.nome == "Lucas Tonnon"


def test_email_repetido(administrador, vendedor):
    with pytest.raises(RegraDeNegocio, match="Já existe um funcionário com este e-mail."):
        criar_funcionario(
            nome="X", email="CARLA@helptoner.com.br", perfil=VENDEDOR, por=administrador
        )


def test_perfil_desconhecido(administrador):
    with pytest.raises(RegraDeNegocio, match="Perfil inválido."):
        criar_funcionario(nome="X", email="x@helptoner.com.br", perfil="Gerente", por=administrador)


def test_alterar_perfil_registra_o_motivo(administrador, vendedor):
    alterar_funcionario(vendedor, nome="Carla Souza", perfil=ADMINISTRADOR, por=administrador)
    vendedor = Usuario.objects.get(pk=vendedor.pk)
    assert vendedor.perfil == ADMINISTRADOR
    assert list(vendedor.groups.values_list("name", flat=True)) == [ADMINISTRADOR]
    registro = vendedor.history.first()
    assert registro.history_change_reason == "Perfil: Vendedor → Administrador"
    assert registro.history_user == administrador


def test_alterar_so_o_nome_fica_sem_motivo(administrador, vendedor):
    alterar_funcionario(vendedor, nome="Carla Souza Lima", perfil=VENDEDOR, por=administrador)
    registro = Usuario.objects.get(pk=vendedor.pk).history.first()
    assert registro.nome == "Carla Souza Lima" and registro.history_change_reason is None
    assert registro.history_user == administrador


def test_alterar_nome_e_perfil_registra_os_dois(administrador, vendedor):
    # O histórico (Tarefa 22) usa o motivo no lugar das diferenças: com um registro só, a troca
    # de nome sumiria. Por isso, nome e perfil ficam em registros separados.
    alterar_funcionario(vendedor, nome="Carla Lima", perfil=ADMINISTRADOR, por=administrador)
    perfil, nome = Usuario.objects.get(pk=vendedor.pk).history.all()[:2]
    assert perfil.history_change_reason == "Perfil: Vendedor → Administrador"
    assert nome.nome == "Carla Lima" and nome.history_change_reason is None


def test_alterar_sem_mudanca_nao_grava_historico(administrador, vendedor):
    antes = vendedor.history.count()
    alterar_funcionario(vendedor, nome="Carla Souza", perfil=VENDEDOR, por=administrador)
    assert vendedor.history.count() == antes


def test_redefinir_senha_derruba_a_sessao(client, administrador, vendedor):
    client.force_login(vendedor)
    senha = redefinir_senha(vendedor, por=administrador)
    assert client.get("/")["Location"].startswith("/contas/login/")
    vendedor.refresh_from_db()
    assert vendedor.deve_trocar_senha and vendedor.check_password(senha)
    registro = vendedor.history.first()
    assert registro.history_change_reason == "Senha redefinida"
    assert registro.history_user == administrador


def test_zerar_2fa_leva_de_volta_a_configuracao(client, administrador, vendedor):
    zerar_2fa(vendedor, por=administrador)
    assert not Authenticator.objects.filter(user=vendedor).exists()  # TOTP e códigos
    vendedor.refresh_from_db()
    assert not vendedor.codigos_recuperacao_entregues
    registro = vendedor.history.first()
    assert registro.history_change_reason == "Verificação em duas etapas zerada"
    assert registro.history_user == administrador
    client.force_login(vendedor)  # o próximo acesso
    assert client.get("/")["Location"] == "/contas/2fa/totp/activate/"


def test_desativar_tira_o_acesso_na_hora(client, administrador, vendedor):
    client.force_login(vendedor)
    desativar_funcionario(vendedor, por=administrador)
    assert client.get("/")["Location"].startswith("/contas/login/")
    vendedor.refresh_from_db()
    assert not vendedor.is_active
    registro = vendedor.history.first()
    assert registro.history_change_reason == "Funcionário desativado"
    assert registro.history_user == administrador


def test_desativar_duas_vezes_nao_repete_o_historico(administrador, vendedor):
    desativar_funcionario(vendedor, por=administrador)
    antes = vendedor.history.count()
    desativar_funcionario(Usuario.objects.get(pk=vendedor.pk), por=administrador)
    assert vendedor.history.count() == antes


def test_administrador_nao_mexe_em_si_mesmo(administrador):
    with pytest.raises(RegraDeNegocio, match="Você não pode desativar a si mesmo."):
        desativar_funcionario(administrador, por=administrador)
    with pytest.raises(RegraDeNegocio, match="Você não pode mudar o seu próprio perfil."):
        alterar_funcionario(administrador, nome="Lucas", perfil=VENDEDOR, por=administrador)
    administrador.refresh_from_db()
    assert administrador.is_active and administrador.eh_administrador
    assert administrador.nome == "Lucas Tonnon"


def test_administrador_muda_o_proprio_nome(administrador):
    alterar_funcionario(administrador, nome="Lucas T.", perfil=ADMINISTRADOR, por=administrador)
    administrador.refresh_from_db()
    assert administrador.nome == "Lucas T."


@pytest.mark.parametrize(
    "acao",
    [
        lambda u, por: alterar_funcionario(u, nome="Carla S.", perfil=VENDEDOR, por=por),
        lambda u, por: redefinir_senha(u, por=por),
        lambda u, por: zerar_2fa(u, por=por),
    ],
    ids=["alterar", "redefinir_senha", "zerar_2fa"],
)
def test_acao_nao_desfaz_uma_desativacao_feita_ao_mesmo_tempo(administrador, vendedor, acao):
    # `vendedor` foi lido antes de outro administrador desativá-lo (§4.2: perde o acesso na hora).
    Usuario.objects.filter(pk=vendedor.pk).update(is_active=False)
    acao(vendedor, administrador)
    assert not Usuario.objects.get(pk=vendedor.pk).is_active


def test_desativar_encerra_as_sessoes_abertas(client, client_admin, administrador, vendedor):
    # §4.2: "as sessões são invalidadas" (Ruling R16). Só as do funcionário desativado.
    client.force_login(vendedor)
    Client().force_login(vendedor)  # outro navegador
    assert len(_sessoes_de(vendedor)) == 2
    desativar_funcionario(vendedor, por=administrador)
    assert _sessoes_de(vendedor) == [] and _sessoes_de(administrador)
    assert client_admin.get("/").status_code == 200
    # Reativado depois (pelo painel), a sessão antiga não volta a valer.
    Usuario.objects.filter(pk=vendedor.pk).update(is_active=True)
    assert client.get("/")["Location"].startswith("/contas/login/")


def test_zerar_2fa_encerra_as_sessoes_abertas(client, client_admin, administrador, vendedor):
    # Revisão final (I1): o celular perdido ou roubado não continua logado. Senão, ele seria
    # levado à ativação do autenticador e poderia cadastrar outro aplicativo na conta.
    client.force_login(vendedor)
    Client().force_login(vendedor)  # outro navegador
    assert len(_sessoes_de(vendedor)) == 2
    zerar_2fa(vendedor, por=administrador)
    assert _sessoes_de(vendedor) == [] and _sessoes_de(administrador)
    assert client.get("/")["Location"].startswith("/contas/login/")
    assert client_admin.get("/").status_code == 200


# Ruling R15: um Administrador comum que zera o 2FA, redefine a senha ou rebaixa um superusuário
# tira dele o acesso ao painel. Senão, poderia tomar a conta (2FA zerado + senha conhecida) e
# entrar no painel, que é só do superusuário (§4.3).
@pytest.mark.parametrize(
    "acao,motivo",
    [
        (lambda u, por: zerar_2fa(u, por=por), "Verificação em duas etapas zerada"),
        (lambda u, por: redefinir_senha(u, por=por), "Senha redefinida"),
        (
            lambda u, por: alterar_funcionario(u, nome=u.nome, perfil=VENDEDOR, por=por),
            "Perfil: Administrador → Vendedor",
        ),
    ],
    ids=["zerar_2fa", "redefinir_senha", "rebaixar"],
)
def test_administrador_comum_tira_o_painel_do_superusuario(administrador, acao, motivo):
    su = _superusuario()
    acao(su, administrador)
    su = Usuario.objects.get(pk=su.pk)
    assert not su.is_superuser and not su.is_staff
    registro = su.history.first()
    assert registro.history_change_reason == motivo + SEM_PAINEL
    assert registro.history_user == administrador


@pytest.mark.parametrize(
    "acao",
    [
        lambda u, por: zerar_2fa(u, por=por),
        lambda u, por: redefinir_senha(u, por=por),
        lambda u, por: alterar_funcionario(u, nome=u.nome, perfil=VENDEDOR, por=por),
    ],
    ids=["zerar_2fa", "redefinir_senha", "rebaixar"],
)
def test_superusuario_agindo_sobre_superusuario_mantem_o_painel(db, acao):
    su = _superusuario()
    outro = _superusuario(email="pai@helptoner.com.br", nome="Pai Super")
    acao(outro, su)
    outro = Usuario.objects.get(pk=outro.pk)
    assert outro.is_superuser and outro.is_staff
    assert SEM_PAINEL not in outro.history.first().history_change_reason


def test_outras_acoes_do_administrador_comum_mantem_o_painel(administrador):
    su = _superusuario()
    alterar_funcionario(su, nome="Lucas S.", perfil=ADMINISTRADOR, por=administrador)
    desativar_funcionario(su, por=administrador)
    su = Usuario.objects.get(pk=su.pk)
    assert su.is_superuser and su.is_staff and not su.is_active and su.nome == "Lucas S."
