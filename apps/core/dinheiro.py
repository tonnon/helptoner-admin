import re
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")
_CASAS_DO_CUSTO = Decimal("0.0001")

# O ponto só separa milhar (em grupos de 3) e a vírgula separa os decimais: "1.234,56".
_NUMERO_BR = re.compile(r"-?(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,[0-9]+)?")


def arredondar(valor: Decimal) -> Decimal:
    """Arredonda um valor em reais para centavos, com o meio para cima (0,005 → 0,01)."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def arredondar_custo(valor: Decimal) -> Decimal:
    """Arredonda um custo para 4 casas, com o meio para cima."""
    return valor.quantize(_CASAS_DO_CUSTO, rounding=ROUND_HALF_UP)


def ler_decimal_br(texto: str) -> Decimal:
    """Lê um número escrito à brasileira ("1.234,56"). Levanta ValueError se não for um."""
    limpo = texto.strip()
    if not _NUMERO_BR.fullmatch(limpo):
        raise ValueError(f"Número inválido: {texto!r}")
    return Decimal(limpo.replace(".", "").replace(",", "."))
