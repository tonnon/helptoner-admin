from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.htmx import eh_htmx

from .buscas import buscar_clientes, normalizar_busca
from .forms import ClienteForm, mensagem_documento_repetido
from .models import Cliente

POR_PAGINA = 20


@require_GET
def clientes(request):
    """Lista (padrão P18): a página abre com o esqueleto e busca as linhas por HTMX."""
    if not eh_htmx(request):
        return render(request, "cadastros/clientes.html")
    texto = normalizar_busca(request.GET.get("q", ""))
    incluir_inativos = request.GET.get("inativos") == "1"
    paginador = Paginator(buscar_clientes(texto, incluir_inativos=incluir_inativos), POR_PAGINA)
    contexto = {
        "pagina": paginador.get_page(request.GET.get("pagina")),
        "sem_clientes": paginador.count == 0 and not Cliente.objects.exists(),
        "q": texto,
        "inativos": incluir_inativos,
    }
    return render(request, "cadastros/clientes.html#resultados", contexto)


def _salvar(form) -> bool:
    """Grava o formulário. Documento criado por outro envio nesse meio tempo vira erro de campo."""
    try:
        with transaction.atomic():
            form.save()
    except IntegrityError:
        outro = Cliente.objects.filter(documento=form.cleaned_data["documento"]).first()
        form.add_error("documento", mensagem_documento_repetido(outro))
        return False
    return True


@require_http_methods(["GET", "POST"])
def cliente_novo(request):
    form = ClienteForm(request.POST if request.method == "POST" else None)
    if form.is_valid() and _salvar(form):
        messages.success(request, "Cliente salvo.")
        return redirect("cadastros:clientes")
    return render(request, "cadastros/cliente_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def cliente_editar(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    form = ClienteForm(request.POST if request.method == "POST" else None, instance=cliente)
    if form.is_valid() and _salvar(form):
        messages.success(request, "Cliente salvo.")
        return redirect("cadastros:clientes")
    return render(request, "cadastros/cliente_form.html", {"form": form, "cliente": cliente})


def _mudar_situacao(request, pk, *, ativo, aviso):
    cliente = get_object_or_404(Cliente, pk=pk)
    if cliente.ativo != ativo:
        cliente.ativo = ativo
        cliente.save(update_fields=["ativo", "atualizado_em"])
    messages.success(request, aviso)
    return redirect("cadastros:cliente_editar", pk=pk)


@require_POST
def cliente_inativar(request, pk):
    return _mudar_situacao(request, pk, ativo=False, aviso="Cliente inativado.")


@require_POST
def cliente_reativar(request, pk):
    return _mudar_situacao(request, pk, ativo=True, aviso="Cliente reativado.")
