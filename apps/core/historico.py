"""Histórico de alterações e de acessos: junta os registros do simple-history e os logins."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from apps.cadastros.models import Cliente, Produto
from apps.contas.models import RegistroAcesso, Usuario
from apps.contas.navegador import navegador_legivel

from .datas import intervalo_de_datas
from .formatacao import VAZIO, brl

TIPOS = (
    ("cliente", "Clientes"),
    ("produto", "Produtos"),
    ("funcionario", "Funcionários"),
    ("login", "Logins"),
)
_VALORES_DE_TIPO = {valor for valor, _ in TIPOS}

# (tipo, modelo, rótulo do objeto, atributo que o identifica, campo de situação)
_FONTES = (
    ("cliente", Cliente, "Cliente", "nome", "ativo"),
    ("produto", Produto, "Produto", "codigo", "ativo"),
    ("funcionario", Usuario, "Funcionário", "nome", "is_active"),
)
_VERBO_DE_CRIACAO = {"cliente": "cadastrado", "produto": "cadastrado", "funcionario": "criado"}
LIMITE_DO_TEXTO = 60
# Campos do Django sem verbose_name em português.
_ROTULOS = {"is_superuser": "superusuário (painel de manutenção)"}


@dataclass(frozen=True)
class Evento:
    quando: datetime
    quem: str
    tipo: str
    descricao: str
    sucesso: bool | None = None

    @property
    def corpo(self) -> str:
        """Nos logins, a descrição sem o selo ("Login · " ou "Login recusado · ")."""
        return self.descricao.partition(" · ")[2] if self.tipo == "login" else self.descricao


def _valor(campo, valor) -> str:
    if valor is None or valor == "":
        return VAZIO
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, Decimal):
        return brl(valor)
    if campo.choices:
        valor = dict(campo.flatchoices).get(valor, valor)
    texto = str(valor)
    if len(texto) > LIMITE_DO_TEXTO:
        texto = texto[: LIMITE_DO_TEXTO - 1] + "…"
    return texto


def _fonte_de(registro):
    modelo = registro.instance_type
    return next(fonte for fonte in _FONTES if fonte[1] is modelo)


def _minuscula_inicial(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def _motivo(motivo: str) -> str:
    # "Funcionário desativado" já vem depois de "Funcionário Fulano:", então a palavra cai.
    if motivo.startswith("Funcionário "):
        motivo = motivo.removeprefix("Funcionário ")
    return _minuscula_inicial(motivo)


def descrever_alteracao(registro, anterior=None) -> str | None:
    """Uma frase para o registro de histórico; None se não há diferença visível nem motivo.

    `anterior` é o registro anterior do mesmo objeto; sem ele, é buscado (uma consulta a mais).
    """
    _, modelo, rotulo, atributo, situacao = _fonte_de(registro)
    sujeito = f"{rotulo} {getattr(registro, atributo)}"
    tipo = _fonte_de(registro)[0]
    if registro.history_type == "+":
        return f"{sujeito} {_VERBO_DE_CRIACAO[tipo]}"
    if registro.history_type == "-":
        return f"{sujeito} excluído"
    motivo = registro.history_change_reason
    if motivo:
        return f"{sujeito}: {_motivo(motivo)}"
    anterior = anterior or registro.prev_record
    if anterior is None:
        return None
    partes = []
    for mudanca in registro.diff_against(anterior).changes:
        if mudanca.field == situacao:
            partes.append("reativado" if mudanca.new else "inativado")
            continue
        campo = modelo._meta.get_field(mudanca.field)
        antes, depois = _valor(campo, mudanca.old), _valor(campo, mudanca.new)
        rotulo_do_campo = _ROTULOS.get(mudanca.field, str(campo.verbose_name).lower())
        partes.append(f"{rotulo_do_campo} {antes} → {depois}")
    if not partes:
        return None
    if partes == ["inativado"] or partes == ["reativado"]:
        return f"{sujeito} {partes[0]}"
    return f"{sujeito}: {'; '.join(partes)}"


def _quem(usuario) -> str:
    return usuario.nome if usuario else VAZIO


def _eventos_de_alteracao(tipo: str, de: datetime, ate: datetime) -> list[Evento]:
    modelo = next(fonte[1] for fonte in _FONTES if fonte[0] == tipo)
    no_periodo = list(
        modelo.history.filter(history_date__gte=de, history_date__lt=ate).select_related(
            "history_user"
        )
    )
    # Os registros anteriores, de uma vez só (evita uma consulta por registro).
    anteriores = defaultdict(list)
    ids = {r.id for r in no_periodo if r.history_type == "~"}
    if ids:
        for r in modelo.history.filter(id__in=ids, history_date__lt=ate).order_by(
            "history_date", "history_id"
        ):
            anteriores[r.id].append(r)
    eventos = []
    for registro in no_periodo:
        anterior = None
        if registro.history_type == "~":
            antes = [r for r in anteriores[registro.id] if r.history_id < registro.history_id]
            anterior = antes[-1] if antes else None
            if anterior is None:
                continue
        descricao = descrever_alteracao(registro, anterior)
        if descricao:
            eventos.append(
                Evento(registro.history_date, _quem(registro.history_user), tipo, descricao)
            )
    return eventos


def _eventos_de_login(de: datetime, ate: datetime) -> list[Evento]:
    registros = RegistroAcesso.objects.filter(quando__gte=de, quando__lt=ate).select_related(
        "usuario"
    )
    eventos = []
    for r in registros:
        if r.sucesso:
            descricao = f"Login · {navegador_legivel(r.navegador)}"
        else:
            motivo = f" ({r.motivo})" if r.motivo else ""
            descricao = f"Login recusado · {r.email_tentado}{motivo}"
        eventos.append(Evento(r.quando, _quem(r.usuario), "login", descricao, r.sucesso))
    return eventos


def eventos(*, tipo: str = "", inicio: date, fim: date) -> list[Evento]:
    """Do mais recente para o mais antigo; `tipo` vazio (ou desconhecido) traz as quatro fontes."""
    de, ate = intervalo_de_datas(inicio, fim)
    tipos = [tipo] if tipo in _VALORES_DE_TIPO else [valor for valor, _ in TIPOS]
    lista = []
    for t in tipos:
        lista += _eventos_de_login(de, ate) if t == "login" else _eventos_de_alteracao(t, de, ate)
    return sorted(lista, key=lambda e: e.quando, reverse=True)
