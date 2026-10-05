import re

from django.db.models import F, Func, Q, QuerySet, Value

from .documentos import normalizar_documento
from .models import Cliente, Produto

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


def buscar_produtos(
    texto: str, *, incluir_inativos: bool = False, limite: int | None = None
) -> QuerySet[Produto]:
    """Produtos por código (também sem pontuação: "tn1060" acha "TN-1060"), descrição ou marca."""
    texto = normalizar_busca(texto)
    produtos = Produto.objects.all()
    if not incluir_inativos:
        produtos = produtos.filter(ativo=True)
    if texto:
        filtro = (
            Q(codigo__icontains=texto)
            | Q(descricao__unaccent__icontains=texto)
            | Q(marca__unaccent__icontains=texto)
        )
        codigo = re.sub(r"[^A-Z0-9]", "", texto.upper())
        if codigo:
            produtos = produtos.annotate(
                codigo_limpo=Func(
                    F("codigo"),
                    Value("[^A-Z0-9]"),
                    Value(""),
                    Value("g"),
                    function="regexp_replace",
                )
            )
            filtro |= Q(codigo_limpo__contains=codigo)
        produtos = produtos.filter(filtro)
    produtos = produtos.order_by("codigo")
    if limite is not None:
        produtos = produtos[:limite]
    return produtos
