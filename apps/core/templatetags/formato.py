from django import template

from apps.core import formatacao

register = template.Library()


def _ou_vazio(funcao):
    """Variável ausente no template chega como "": mostra "—" em vez de quebrar a página."""

    def filtro(valor):
        if valor is None or valor == "":
            return formatacao.VAZIO
        return funcao(valor)

    return filtro


register.filter("brl", _ou_vazio(formatacao.brl))
register.filter("inteiro", _ou_vazio(formatacao.inteiro_br))
register.filter("pedido_numero", _ou_vazio(formatacao.numero_pedido))
register.filter("data_br", _ou_vazio(formatacao.data_br))
register.filter("data_hora_br", _ou_vazio(formatacao.data_hora_br))


@register.filter("pct")
def pct(fracao, casas=1):
    """{{ margem|pct }} → '38,5%'; {{ margem|pct:2 }} → '38,46%'."""
    if fracao is None or fracao == "":
        return formatacao.VAZIO
    return formatacao.percentual(fracao, int(casas))


@register.filter("iniciais")
def iniciais(nome) -> str:
    """'Lucas Tonnon' → 'LT' (primeiro e último nome); 'Carla' → 'C'."""
    partes = str(nome or "").split()
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0][0].upper()
    return (partes[0][0] + partes[-1][0]).upper()
