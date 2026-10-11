from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .datas import FUSO
from .dinheiro import arredondar

VAZIO = "—"


def _trocar_separadores(numero_en: str) -> str:
    """'1,234.5' → '1.234,5'."""
    return numero_en.replace(",", "_").replace(".", ",").replace("_", ".")


def brl(valor: Decimal | None) -> str:
    """'R$ 1.234,50'; negativo vira '-R$ 254,85'; None vira '—'."""
    if valor is None:
        return VAZIO
    centavos = arredondar(Decimal(valor))
    texto = "R$ " + _trocar_separadores(f"{abs(centavos):,.2f}")
    return f"-{texto}" if centavos < 0 else texto


def inteiro_br(n: int) -> str:
    """1234567 → '1.234.567'."""
    return f"{n:,}".replace(",", ".")


def numero_pedido(n: int | None) -> str:
    """1042 → 'nº 1.042'; None (rascunho) → '—'."""
    return VAZIO if n is None else f"nº {inteiro_br(n)}"


def percentual(fracao: Decimal | None, casas: int = 1) -> str:
    """Decimal('0.3846') → '38,5%'; None → '—'."""
    if fracao is None:
        return VAZIO
    valor = (Decimal(fracao) * 100).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    if valor == 0:
        valor = abs(valor)  # sem "-0,0%"
    return _trocar_separadores(f"{valor:,.{casas}f}") + "%"


def _em_brasilia(valor: datetime) -> datetime:
    return valor.astimezone(FUSO) if timezone.is_aware(valor) else valor


def data_br(valor: date | datetime | None) -> str:
    """'02/10/2026'. Data e hora são convertidas para Brasília antes."""
    if valor is None:
        return VAZIO
    if isinstance(valor, datetime):
        valor = _em_brasilia(valor)
    return valor.strftime("%d/%m/%Y")


def data_hora_br(valor: datetime | None) -> str:
    """'31/10/2026 22:30', no horário de Brasília."""
    if valor is None:
        return VAZIO
    return _em_brasilia(valor).strftime("%d/%m/%Y %H:%M")
