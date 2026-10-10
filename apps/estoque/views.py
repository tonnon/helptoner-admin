from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.cadastros.models import Produto
from apps.core.datas import hoje, intervalo_de_datas, ler_data
from apps.core.erros import RegraDeNegocio
from apps.core.htmx import eh_htmx
from apps.core.permissoes import requer_administrador

from . import services
from .forms import AjusteForm, EntradaForm, EstoqueInicialForm
from .models import MovimentoEstoque

POR_PAGINA = 50
DIAS_PADRAO = 30


def _data(texto: str | None, padrao: date) -> date:
    return ler_data(texto) or padrao


def _periodo(request) -> tuple[date, date]:
    fim = _data(request.GET.get("fim"), hoje())
    inicio = _data(request.GET.get("inicio"), fim - timedelta(days=DIAS_PADRAO))
    return inicio, fim


@require_GET
def historico(request):
    """Histórico de movimentos (padrão P18), aberto a todos; custo só para o Administrador."""
    inicio, fim = _periodo(request)
    produto = request.GET.get("produto", "").strip()
    tipo = request.GET.get("tipo", "")
    if not eh_htmx(request):
        contexto = {
            "tipos": MovimentoEstoque.Tipo.choices,
            "inicio": inicio,
            "fim": fim,
            "produto": produto,
            "tipo": tipo,
        }
        return render(request, "estoque/historico.html", contexto)
    de, ate = intervalo_de_datas(inicio, fim)
    lista = MovimentoEstoque.objects.select_related("produto", "usuario", "pedido").filter(
        criado_em__gte=de, criado_em__lt=ate
    )
    if produto:
        lista = lista.filter(produto__codigo__icontains=produto)
    if tipo in MovimentoEstoque.Tipo.values:
        lista = lista.filter(tipo=tipo)
    paginador = Paginator(lista, POR_PAGINA)
    contexto = {"pagina": paginador.get_page(request.GET.get("pagina"))}
    return render(request, "estoque/historico.html#resultados", contexto)


def _codigos(*, sem_movimentos: bool = False) -> list[str]:
    produtos = Produto.objects.filter(ativo=True)
    if sem_movimentos:
        produtos = produtos.exclude(Exists(MovimentoEstoque.objects.filter(produto=OuterRef("pk"))))
    return list(produtos.order_by("codigo").values_list("codigo", flat=True))


def _formulario(request, classe, *, titulo, sem_movimentos=False, confirmar=None, gravar):
    """Fluxo comum dos três formulários.

    `gravar(form)` chama o serviço e devolve o aviso. Uma regra de negócio violada vira erro geral
    do formulário; `confirmar(form)` (opcional) devolve o texto de uma etapa de confirmação.
    """
    form = classe(request.POST if request.method == "POST" else None)
    confirmacao = None
    if form.is_valid():
        if confirmar and not form.cleaned_data.get("confirmar"):
            confirmacao = confirmar(form)
        else:
            try:
                aviso = gravar(form)
            except RegraDeNegocio as erro:
                form.add_error(None, str(erro))
            except Produto.DoesNotExist:
                form.add_error("codigo", "Produto não encontrado.")
            else:
                messages.success(request, aviso)
                return redirect("estoque:historico")
    contexto = {
        "form": form,
        "titulo": titulo,
        "codigos": _codigos(sem_movimentos=sem_movimentos),
        "confirmacao": confirmacao,
    }
    return render(request, "estoque/movimento_form.html", contexto)


@requer_administrador
@require_http_methods(["GET", "POST"])
def entrada(request):
    def gravar(form):
        services.registrar_entrada(
            produto_id=form.produto.pk,
            quantidade=form.cleaned_data["quantidade"],
            custo_unitario=form.cleaned_data["custo_unitario"],
            observacao=form.cleaned_data["observacao"],
            usuario=request.user,
        )
        return f"Entrada registrada: {form.produto.codigo}, {form.cleaned_data['quantidade']} un."

    return _formulario(request, EntradaForm, titulo="Entrada de estoque", gravar=gravar)


@requer_administrador
@require_http_methods(["GET", "POST"])
def inicial(request):
    def gravar(form):
        services.registrar_estoque_inicial(
            produto_id=form.produto.pk,
            quantidade=form.cleaned_data["quantidade"],
            custo_unitario=form.cleaned_data["custo_unitario"],
            usuario=request.user,
        )
        quantidade = form.cleaned_data["quantidade"]
        return f"Estoque inicial registrado: {form.produto.codigo}, {quantidade} un."

    return _formulario(
        request, EstoqueInicialForm, titulo="Estoque inicial", sem_movimentos=True, gravar=gravar
    )


@requer_administrador
@require_http_methods(["GET", "POST"])
def ajuste(request):
    def confirmar(form):
        delta = form.delta
        sinal = f"+{delta}" if delta > 0 else f"−{-delta}"
        return (
            f"Confirme o ajuste: {sinal} em {form.produto.codigo} "
            f"(motivo: {form.cleaned_data['motivo']})"
        )

    def gravar(form):
        services.registrar_ajuste(
            produto_id=form.produto.pk,
            delta=form.delta,
            motivo=form.cleaned_data["motivo"],
            usuario=request.user,
        )
        sinal = f"+{form.delta}" if form.delta > 0 else f"−{-form.delta}"
        return f"Ajuste registrado: {form.produto.codigo} {sinal}"

    return _formulario(
        request, AjusteForm, titulo="Ajuste de estoque", confirmar=confirmar, gravar=gravar
    )
