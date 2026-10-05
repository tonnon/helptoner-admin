import re

from django.db.models import Q, QuerySet

from .documentos import normalizar_documento
from .models import Cliente

TAMANHO_MAXIMO = 100
MINIMO_DOCUMENTO = 3


def normalizar_busca(texto: str) -> str:
    """Tira espaços das pontas, junta espaços repetidos e corta em 100 caracteres."""
    return re.sub(r"\s+", " ", texto or "").strip()[:TAMANHO_MAXIMO]


def buscar_clientes(
    texto: str, *, incluir_inativos: bool = False, limite: int | None = None
) -> QuerySet[Cliente]:
    """Clientes por nome (sem acento, sem diferença de maiúsculas) ou por parte do CPF/CNPJ."""
    texto = normalizar_busca(texto)
    clientes = Cliente.objects.all()
    if not incluir_inativos:
        clientes = clientes.filter(ativo=True)
    if texto:
        filtro = Q(nome__unaccent__icontains=texto)
        documento = normalizar_documento(texto)
        if len(documento) >= MINIMO_DOCUMENTO:
            filtro |= Q(documento__contains=documento)
        clientes = clientes.filter(filtro)
    if limite is not None:
        clientes = clientes[:limite]
    return clientes
