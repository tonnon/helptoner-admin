"""CPF e CNPJ (inclusive o CNPJ alfanumérico da Receita Federal, IN RFB 2.229/2024)."""

import re

from django.core.exceptions import ValidationError

_CNPJ_BASE = re.compile(r"[0-9A-Z]{12}")


def normalizar_documento(texto: str) -> str:
    """Tira tudo que não for letra ou dígito e passa para maiúsculas."""
    return re.sub(r"[^0-9A-Za-z]", "", texto or "").upper()


def _digito(valores: list[int], pesos: list[int]) -> int:
    resto = sum(v * p for v, p in zip(valores, pesos, strict=True)) % 11
    return 0 if resto < 2 else 11 - resto


def digitos_verificadores_cpf(base9: str) -> str:
    valores = [int(c) for c in base9]
    d1 = _digito(valores, list(range(10, 1, -1)))
    d2 = _digito([*valores, d1], list(range(11, 1, -1)))
    return f"{d1}{d2}"


def _pesos_cnpj(tamanho: int) -> list[int]:
    # 2..9 da direita para a esquerda, recomeçando depois do 9.
    return [(i % 8) + 2 for i in range(tamanho - 1, -1, -1)]


def digitos_verificadores_cnpj(base12: str) -> str:
    valores = [ord(c) - 48 for c in base12]
    d1 = _digito(valores, _pesos_cnpj(12))
    d2 = _digito([*valores, d1], _pesos_cnpj(13))
    return f"{d1}{d2}"


def cpf_valido(doc: str) -> bool:
    if not (len(doc) == 11 and doc.isascii() and doc.isdigit()):
        return False
    if len(set(doc)) == 1:
        return False
    return digitos_verificadores_cpf(doc[:9]) == doc[9:]


def cnpj_valido(doc: str) -> bool:
    if len(doc) != 14 or not _CNPJ_BASE.fullmatch(doc[:12]):
        return False
    if not (doc[12:].isascii() and doc[12:].isdigit()):
        return False
    if len(set(doc)) == 1:
        return False
    return digitos_verificadores_cnpj(doc[:12]) == doc[12:]


def validar_documento(tipo: str, texto: str) -> str:
    doc = normalizar_documento(texto)
    if tipo == "PF":
        if not cpf_valido(doc):
            raise ValidationError("CPF inválido: confira os dígitos.")
    elif not cnpj_valido(doc):
        raise ValidationError("CNPJ inválido: confira os dígitos.")
    return doc


def formatar_documento(tipo: str, doc: str) -> str:
    if tipo == "PF" and len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    if tipo == "PJ" and len(doc) == 14:
        return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
    return doc
