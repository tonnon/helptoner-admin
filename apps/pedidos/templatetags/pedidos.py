import unicodedata
from decimal import Decimal

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import SafeString

register = template.Library()


def _sem_acento(texto: str) -> str:
    """Minúsculas, sem acentos (NFD sem as marcas combinantes): "João" → "joao"."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


@register.filter
def realce(texto, busca) -> SafeString:
    """Escapa o texto e marca com <mark> o primeiro trecho igual à busca.

    Não diferencia acentos nem maiúsculas: {{ "João da Silva"|realce:"joao" }} →
    "<mark>João</mark> da Silva". Cada caractere do texto vira a sua forma sem acento (que pode
    ter 0, 1 ou mais caracteres) e guarda de qual posição do original veio; a busca é feita nessa
    versão e o trecho achado é marcado no texto original.
    """
    texto, busca = str(texto or ""), _sem_acento(str(busca or ""))
    simples, origem = [], []
    for posicao, caractere in enumerate(texto):
        for c in _sem_acento(caractere):
            simples.append(c)
            origem.append(posicao)
    achado = "".join(simples).find(busca) if busca else -1
    if achado < 0:
        return escape(texto)
    inicio, fim = origem[achado], origem[achado + len(busca) - 1] + 1
    return format_html("{}<mark>{}</mark>{}", texto[:inicio], texto[inicio:fim], texto[fim:])


@register.filter
def centavos(valor) -> int:
    """Valor em reais como número inteiro de centavos: Decimal("341.82") → 34182."""
    return int((Decimal(valor) * 100).to_integral_value())
