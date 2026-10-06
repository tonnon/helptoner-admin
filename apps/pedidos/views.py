from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.core.datas import hoje
from apps.core.erros import RegraDeNegocio
from apps.core.formatacao import numero_pedido
from apps.core.htmx import eh_htmx
from apps.core.permissoes import requer_administrador

from .consultas import filtrar_pedidos, lucro_do_pedido
from .models import Pedido
from .services import MOTIVO_MAXIMO, cancelar_pedido

POR_PAGINA = 20
MESES_NO_FILTRO = 12


def _meses() -> list[tuple[str, str]]:
    """Os últimos 12 meses, do atual para trás, como ("AAAA-MM", "MM/AAAA")."""
    dia = hoje()
    ano, mes = dia.year, dia.month
    meses = []
    for _ in range(MESES_NO_FILTRO):
        meses.append((f"{ano}-{mes:02d}", f"{mes:02d}/{ano}"))
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return meses


@require_GET
def lista(request):
    """Lista (padrão P18) de todos os pedidos, aberta a todos os perfis."""
    if not eh_htmx(request):
        return render(request, "pedidos/lista.html", {"meses": _meses()})
    busca = request.GET.get("busca", "")
    paginador = Paginator(
        filtrar_pedidos(
            busca=busca, status=request.GET.get("status", ""), mes=request.GET.get("mes", "")
        ),
        POR_PAGINA,
    )
    contexto = {
        "pagina": paginador.get_page(request.GET.get("pagina")),
        "sem_pedidos": paginador.count == 0 and not Pedido.objects.exists(),
    }
    return render(request, "pedidos/lista.html#resultados", contexto)


@require_GET
def detalhe(request, pk):
    pedido = get_object_or_404(
        Pedido.objects.select_related("cliente", "criado_por", "confirmado_por", "cancelado_por"),
        pk=pk,
    )
    itens = list(pedido.itens.all())
    contexto = {"pedido": pedido, "itens": itens}
    if request.user.eh_administrador:  # lucro e margem só são calculados para o Administrador
        if pedido.status != Pedido.Status.RASCUNHO:  # o custo só é gravado na confirmação
            contexto["lucro"], contexto["margem"] = lucro_do_pedido(pedido)
        contexto["motivo_max"] = MOTIVO_MAXIMO
        contexto["titulo_cancelar"] = f"Cancelar pedido {numero_pedido(pedido.numero)}?"
        contexto["texto_cancelar"] = f"O estoque dos {len(itens)} produtos volta."
    return render(request, "pedidos/detalhe.html", contexto)


@requer_administrador
@require_POST
def cancelar(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    try:
        cancelar_pedido(pedido.pk, request.POST.get("motivo", ""), request.user)
    except RegraDeNegocio as erro:
        messages.error(request, erro.mensagem)
    else:
        messages.success(
            request, f"Pedido {numero_pedido(pedido.numero)} cancelado. O estoque voltou."
        )
    return redirect("pedidos:detalhe", pk=pk)
