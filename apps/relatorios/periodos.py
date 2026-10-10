"""Períodos e filtros dos relatórios (módulo puro, sem banco)."""

import calendar
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from urllib.parse import urlencode

DATA_MINIMA = date(2000, 1, 1)
DATA_MAXIMA = date(2100, 12, 31)
MAXIMO_DIAS_POR_DIA = 366
DIAS_SEM_COMPRAR = 60
MAXIMO_DIAS_SEM_COMPRAR = 3650


class Atalho(StrEnum):
    TRES_MESES = "3m"
    ANO = "ano"
    DOZE_MESES = "12m"
    DATAS = "datas"


class Agrupamento(StrEnum):
    DIA = "dia"
    SEMANA = "semana"
    MES = "mes"


NOMES_DO_AGRUPAMENTO = {
    Agrupamento.DIA: "dia",
    Agrupamento.SEMANA: "semana",
    Agrupamento.MES: "mês",
}


@dataclass(frozen=True)
class Filtros:
    inicio: date
    fim: date
    agrupamento: Agrupamento
    funcionario_id: int | None
    atalho: Atalho

    def como_querystring(self) -> str:
        """Querystring que `ler_filtros` lê de volta para os mesmos filtros."""
        pares = {"atalho": self.atalho.value, "agrupamento": self.agrupamento.value}
        if self.atalho == Atalho.DATAS:
            pares["inicio"] = self.inicio.isoformat()
            pares["fim"] = self.fim.isoformat()
        if self.funcionario_id is not None:
            pares["funcionario"] = str(self.funcionario_id)
        return urlencode(pares)

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1


def deslocar_meses(dia: date, meses: int) -> date:
    """Anda `meses` meses; se o dia não existir no mês de destino, usa o último dia dele."""
    total = dia.year * 12 + (dia.month - 1) + meses
    ano, mes = divmod(total, 12)
    mes += 1
    return dia.replace(year=ano, month=mes, day=min(dia.day, calendar.monthrange(ano, mes)[1]))


def periodo_do_atalho(atalho: Atalho, hoje: date) -> tuple[date, date]:
    """Os atalhos incluem o mês atual (P16)."""
    if atalho == Atalho.TRES_MESES:
        return deslocar_meses(hoje.replace(day=1), -2), hoje
    if atalho == Atalho.ANO:
        return date(hoje.year, 1, 1), hoje
    if atalho == Atalho.DOZE_MESES:
        return deslocar_meses(hoje.replace(day=1), -11), hoje
    raise ValueError(f"O atalho {atalho!r} não tem período fixo.")


def periodo_anterior(f: Filtros) -> Filtros:
    """O período comparável anterior: deslocado 3 ou 12 meses, ou o mesmo número de dias antes."""
    if f.atalho == Atalho.TRES_MESES:
        inicio, fim = deslocar_meses(f.inicio, -3), deslocar_meses(f.fim, -3)
    elif f.atalho in (Atalho.ANO, Atalho.DOZE_MESES):
        inicio, fim = deslocar_meses(f.inicio, -12), deslocar_meses(f.fim, -12)
    else:
        fim = f.inicio - timedelta(days=1)
        inicio = fim - timedelta(days=f.dias - 1)
    return replace(f, inicio=inicio, fim=fim)


def descricao_comparacao(f: Filtros) -> str:
    if f.atalho == Atalho.TRES_MESES:
        return "vs 3 meses anteriores"
    if f.atalho == Atalho.DOZE_MESES:
        return "vs 12 meses anteriores"
    if f.atalho == Atalho.ANO:
        return f"vs mesmo período de {f.inicio.year - 1}"
    if f.dias == 1:
        return "vs 1 dia anterior"
    return f"vs {f.dias} dias anteriores"


def _ler_data(texto: str) -> date | None:
    texto = (texto or "").strip()
    if len(texto) != 10:
        return None
    try:
        dia = date.fromisoformat(texto)
    except ValueError:
        return None
    return dia if DATA_MINIMA <= dia <= DATA_MAXIMA else None


def ler_filtros(dados: Mapping[str, str], hoje: date) -> tuple[Filtros, list[str]]:
    """Lê os filtros da querystring; o que vier errado gera mensagem e volta ao padrão."""
    erros: list[str] = []

    atalho = Atalho.DOZE_MESES
    bruto = (dados.get("atalho") or "").strip()
    if bruto:
        try:
            atalho = Atalho(bruto)
        except ValueError:
            erros.append("Período inválido.")

    if atalho == Atalho.DATAS:
        data_inicial = _ler_data(dados.get("inicio", ""))
        data_final = _ler_data(dados.get("fim", ""))
        erros_datas = []
        if data_inicial is None:
            erros_datas.append("Data inicial inválida.")
        if data_final is None:
            erros_datas.append("Data final inválida.")
        if data_inicial and data_final and data_inicial > data_final:
            erros_datas.append("A data inicial precisa ser antes da final.")
        if erros_datas:
            erros += erros_datas
            atalho = Atalho.DOZE_MESES
            inicio, fim = periodo_do_atalho(atalho, hoje)
        else:
            inicio, fim = data_inicial, data_final
    else:
        inicio, fim = periodo_do_atalho(atalho, hoje)

    agrupamento = Agrupamento.MES
    bruto = (dados.get("agrupamento") or "").strip()
    if bruto:
        try:
            agrupamento = Agrupamento(bruto)
        except ValueError:
            erros.append("Agrupamento inválido.")
    if agrupamento == Agrupamento.DIA and (fim - inicio).days + 1 > MAXIMO_DIAS_POR_DIA:
        erros.append("Para agrupar por dia, escolha um período de até 366 dias.")
        agrupamento = Agrupamento.MES

    funcionario_id = None
    bruto = (dados.get("funcionario") or "").strip()
    if bruto:
        if bruto.isascii() and bruto.isdigit() and len(bruto) <= 9 and int(bruto) > 0:
            funcionario_id = int(bruto)
        else:
            erros.append("Funcionário inválido.")

    return Filtros(inicio, fim, agrupamento, funcionario_id, atalho), erros


def ler_dias_sem_comprar(dados: Mapping[str, str]) -> tuple[int, list[str]]:
    """O X de "clientes sem comprar há mais de X dias" (aba Clientes); se vier errado, fica 60."""
    bruto = (dados.get("dias") or "").strip()
    if not bruto:
        return DIAS_SEM_COMPRAR, []
    if bruto.isascii() and bruto.isdigit() and len(bruto) <= 4:
        dias = int(bruto)
        if 1 <= dias <= MAXIMO_DIAS_SEM_COMPRAR:
            return dias, []
    return DIAS_SEM_COMPRAR, ["Número de dias inválido."]
