import calendar
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje(agora: datetime | None = None) -> date:
    """O dia de hoje em Brasília (às 22h30 de 31/10 ainda é 31/10, mesmo já sendo 01/11 em UTC)."""
    return (agora or timezone.now()).astimezone(FUSO).date()


def intervalo_de_datas(inicio: date, fim: date) -> tuple[datetime, datetime]:
    """Do começo de `inicio` ao começo do dia seguinte a `fim`, em Brasília, convertidos para UTC.

    O fim fica de fora: filtre com `>= inicio` e `< fim`.
    """
    comeco = datetime.combine(inicio, time.min, tzinfo=FUSO)
    depois_do_fim = datetime.combine(fim + timedelta(days=1), time.min, tzinfo=FUSO)
    return comeco.astimezone(UTC), depois_do_fim.astimezone(UTC)


def mes_de(dia: date) -> tuple[date, date]:
    """O primeiro e o último dia do mês de `dia`."""
    ultimo = calendar.monthrange(dia.year, dia.month)[1]
    return dia.replace(day=1), dia.replace(day=ultimo)
