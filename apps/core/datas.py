import calendar
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

FUSO = ZoneInfo("America/Sao_Paulo")

# Datas aceitas nos filtros. Fora disso, as contas com a data (o dia seguinte, o fuso) podem
# passar do limite do Python (ano 9999) e dar erro 500.
DATA_MINIMA, DATA_MAXIMA = date(2000, 1, 1), date(2100, 12, 31)


def hoje(agora: datetime | None = None) -> date:
    """O dia de hoje em Brasília (às 22h30 de 31/10 ainda é 31/10, mesmo já sendo 01/11 em UTC)."""
    return (agora or timezone.now()).astimezone(FUSO).date()


def ler_data(texto: str | None) -> date | None:
    """A data "AAAA-MM-DD" de um filtro, de 2000 a 2100. Qualquer outra coisa vira None."""
    texto = (texto or "").strip()
    if len(texto) != 10:
        return None
    try:
        dia = date.fromisoformat(texto)
    except ValueError:
        return None
    return dia if DATA_MINIMA <= dia <= DATA_MAXIMA else None


def ler_mes(texto: str | None) -> date | None:
    """O primeiro dia do mês "AAAA-MM" de um filtro, de 2000 a 2100. Qualquer outra coisa vira
    None."""
    try:
        dia = datetime.strptime(texto or "", "%Y-%m").date()
    except ValueError:
        return None
    return dia if DATA_MINIMA <= dia <= DATA_MAXIMA else None


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
