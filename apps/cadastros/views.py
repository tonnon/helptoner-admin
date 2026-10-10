from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.htmx import eh_htmx
from apps.core.permissoes import exigir_administrador, requer_administrador

from .buscas import buscar_clientes, buscar_produtos, normalizar_busca
from .forms import ClienteForm, ProdutoForm, mensagem_documento_repetido
from .models import Cliente, Produto

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


def _gravar(form) -> None:
    """Grava o formulário (chamar dentro de transaction.atomic). Na edição, só os campos da tela.

    Os outros campos (situação, estoque, custo médio) podem ter mudado em outra tela depois que
    esta abriu. Eles são relidos do banco com a linha travada até o fim da transação, para que
    nem o banco nem o histórico voltem ao valor antigo.
    """
    objeto = form.instance
    if objeto.pk is None:
        form.save()
        return
    campos = list(form._meta.fields)
    outros = [
        campo.name
        for campo in objeto._meta.concrete_fields
        if not campo.primary_key and campo.name not in campos
    ]
    objeto.refresh_from_db(fields=outros, from_queryset=type(objeto).objects.select_for_update())
    objeto.save(update_fields=[*campos, "atualizado_em"])


def _salvar(form) -> bool:
    """Grava o formulário. Documento criado por outro envio nesse meio tempo vira erro de campo."""
    try:
        with transaction.atomic():
            _gravar(form)
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


@require_GET
def produtos(request):
    """Lista (padrão P18) de produtos, aberta a todos; custo médio só para o Administrador."""
    if not eh_htmx(request):
        return render(request, "cadastros/produtos.html", {"marcas": _marcas()})
    texto = normalizar_busca(request.GET.get("q", ""))
    marca = request.GET.get("marca", "")
    incluir_inativos = request.GET.get("inativos") == "1"
    lista = buscar_produtos(texto, incluir_inativos=incluir_inativos)
    if marca:
        lista = lista.filter(marca=marca)
    paginador = Paginator(lista, POR_PAGINA)
    contexto = {
        "pagina": paginador.get_page(request.GET.get("pagina")),
        "sem_produtos": paginador.count == 0 and not Produto.objects.exists(),
        "q": texto,
        "marca": marca,
        "inativos": incluir_inativos,
    }
    return render(request, "cadastros/produtos.html#resultados", contexto)


def _marcas() -> list[str]:
    return list(Produto.objects.order_by("marca").values_list("marca", flat=True).distinct())


def _salvar_produto(form) -> bool:
    """Grava o formulário. Código criado por outro envio nesse meio tempo vira erro de campo."""
    try:
        with transaction.atomic():
            _gravar(form)
    except IntegrityError:
        form.add_error("codigo", Produto._meta.get_field("codigo").error_messages["unique"])
        return False
    return True


@requer_administrador
@require_http_methods(["GET", "POST"])
def produto_novo(request):
    form = ProdutoForm(request.POST if request.method == "POST" else None)
    if form.is_valid() and _salvar_produto(form):
        messages.success(request, "Produto salvo.")
        return redirect("cadastros:produtos")
    return render(request, "cadastros/produto_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def produto_editar(request, pk):
    """Todos consultam; só o Administrador grava (conferido antes de olhar o formulário)."""
    if request.method == "POST":
        exigir_administrador(request.user)
    produto = get_object_or_404(Produto, pk=pk)
    if not request.user.eh_administrador:
        return render(request, "cadastros/produto_form.html", {"produto": produto})
    form = ProdutoForm(request.POST if request.method == "POST" else None, instance=produto)
    if form.is_valid() and _salvar_produto(form):
        messages.success(request, "Produto salvo.")
        return redirect("cadastros:produtos")
    return render(request, "cadastros/produto_form.html", {"form": form, "produto": produto})


def _mudar_situacao_produto(request, pk, *, ativo, aviso):
    produto = get_object_or_404(Produto, pk=pk)
    if produto.ativo != ativo:
        produto.ativo = ativo
        produto.save(update_fields=["ativo", "atualizado_em"])
    messages.success(request, aviso)
    return redirect("cadastros:produto_editar", pk=pk)


@requer_administrador
@require_POST
def produto_inativar(request, pk):
    return _mudar_situacao_produto(request, pk, ativo=False, aviso="Produto inativado.")


@requer_administrador
@require_POST
def produto_reativar(request, pk):
    return _mudar_situacao_produto(request, pk, ativo=True, aviso="Produto reativado.")
