from django import template

from apps.cadastros.documentos import formatar_documento

register = template.Library()


@register.filter
def documento(valor, tipo):
    """{{ cliente.documento|documento:cliente.tipo }}"""
    return formatar_documento(tipo, valor or "")
