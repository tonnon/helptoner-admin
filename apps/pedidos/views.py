import json
import logging
from dataclasses import dataclass
from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers, patch_cache_control
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST

from apps.cadastros.buscas import buscar_clientes, buscar_produtos, normalizar_busca
from apps.cadastros.models import Cliente, Produto
from apps.core.datas import hoje
from apps.core.erros import EstoqueInsuficiente, RegraDeNegocio
from apps.core.formatacao import numero_pedido
from apps.core.htmx import avisar, eh_htmx, redirecionar
from apps.core.permissoes import requer_administrador

from . import services
from .consultas import avisos_do_rascunho, filtrar_pedidos, lucro_do_pedido
from .forms import (
    MSG_ESCOLHA_CLIENTE,
    MSG_ESCOLHA_PRODUTO,
    ClienteForm,
    DescontoForm,
    ItemForm,
    QuantidadeForm,
)
from .models import Pedido
from .pdf import gerar_pdf_pedido
from .services import MOTIVO_MAXIMO, MSG_QUANTIDADE_MAXIMA, cancelar_pedido, pode_editar

log_pdf = logging.getLogger("helptoner.pdf")

POR_PAGINA = 20
MESES_NO_FILTRO = 12
LIMITE_SUGESTOES = 6


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
    contexto = {"pedido": pedido, "itens": itens, "pode_editar": pode_editar(pedido, request.user)}
    if request.user.eh_administrador:  # lucro e margem só são calculados para o Administrador
        if pedido.status != Pedido.Status.RASCUNHO:  # o custo só é gravado na confirmação
            contexto["lucro"], contexto["margem"] = lucro_do_pedido(pedido)
        contexto["motivo_max"] = MOTIVO_MAXIMO
        contexto["titulo_cancelar"] = f"Cancelar pedido {numero_pedido(pedido.numero)}?"
        contexto["texto_cancelar"] = (
            "O estoque do produto volta."
            if len(itens) == 1
            else f"O estoque dos {len(itens)} produtos volta."
        )
    return render(request, "pedidos/detalhe.html", contexto)


@require_GET
def baixar_pdf(request, pk):
    """O PDF do pedido, para todos os perfis. O rascunho não tem número, então não tem PDF."""
    pedido = get_object_or_404(
        Pedido.objects.select_related("cliente", "criado_por", "cancelado_por"), pk=pk
    )
    if pedido.status == Pedido.Status.RASCUNHO:
        return _voltar_ao_detalhe(
            request, pedido, "O PDF fica disponível depois de confirmar o pedido."
        )
    try:
        dados = gerar_pdf_pedido(pedido)
    except Exception:
        # O Sentry recebe pela integração de logging; o log leva só o id interno, sem dado pessoal.
        log_pdf.exception("Falha ao gerar o PDF do pedido %s", pedido.pk)
        return _voltar_ao_detalhe(
            request,
            pedido,
            "Não foi possível gerar o PDF. Tente de novo; se continuar, avise o administrador.",
        )
    resposta = HttpResponse(dados, content_type="application/pdf")
    resposta["Content-Disposition"] = content_disposition_header(
        True, f"pedido-{pedido.numero}.pdf"
    )
    add_never_cache_headers(
        resposta
    )  # dados pessoais (LGPD): nada de cache do navegador ou de proxy
    patch_cache_control(resposta, private=True)
    return resposta


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


@require_POST
def repetir(request, pk):
    original = get_object_or_404(Pedido, pk=pk)
    try:
        novo = services.repetir_pedido(original.pk, request.user)
    except RegraDeNegocio as erro:
        return _voltar_ao_detalhe(request, original, erro.mensagem)
    messages.success(
        request, f"Novo rascunho com os itens do pedido {numero_pedido(original.numero)}."
    )
    return redirecionar(request, reverse("pedidos:editar", args=[novo.pk]))


# ---------- Editor do rascunho (novo pedido) ----------
#
# Cada ação de mudança responde com o pedaço "atualizacao" de pedidos/editor.html. Um campo de
# digitação só é redesenhado pela resposta da sua própria ação (ou de uma ação em que ninguém
# está digitando nele), para a resposta não apagar o que a pessoa digita em outro campo.


@dataclass(frozen=True)
class NovoItem:
    """O formulário de incluir item como ele deve aparecer na tela."""

    busca: str = ""
    produto_id: str = ""
    quantidade: str = "1"
    campo_com_erro: str = ""  # "produto" ou "quantidade"
    foco: str = ""  # campo com autofocus: "produto" ou "quantidade"
    produto: Produto | None = None  # para a linha "R$ 189,90 cada · 12 em estoque"
    no_pedido: int = 0


@dataclass(frozen=True)
class ProdutoSugerido:
    produto: Produto
    no_pedido: int  # quanto deste produto já está no rascunho

    @property
    def disponivel(self) -> int:
        return max(self.produto.estoque - self.no_pedido, 0)


def _motivo_sem_edicao(pedido: Pedido) -> str:
    if pedido.status == Pedido.Status.CONFIRMADO:
        numero = numero_pedido(pedido.numero)
        return f"O pedido {numero} já foi confirmado e não pode mais ser editado."
    if pedido.status == Pedido.Status.CANCELADO:
        return f"O pedido {numero_pedido(pedido.numero)} foi cancelado e não pode ser editado."
    return "Só quem criou o rascunho ou um administrador pode editá-lo."


def _voltar_ao_detalhe(request, pedido: Pedido, mensagem: str):
    messages.error(request, mensagem)
    return redirecionar(request, reverse("pedidos:detalhe", args=[pedido.pk]))


def _no_rascunho(view):
    """Abre o rascunho para uma ação do editor: 404 se não existe, 403 se a pessoa não pode mexer
    nele. Se já não é rascunho (confirmado em outra aba, por exemplo), volta ao detalhe com o
    aviso. A view recebe o pedido no lugar do pk."""

    @wraps(view)
    def envolvida(request, pk, **kwargs):
        pedido = get_object_or_404(Pedido, pk=pk)
        if pedido.status != Pedido.Status.RASCUNHO:
            return _voltar_ao_detalhe(request, pedido, _motivo_sem_edicao(pedido))
        if not pode_editar(pedido, request.user):
            raise PermissionDenied
        return view(request, pedido, **kwargs)

    return envolvida


def _contexto_do_editor(pedido: Pedido, **extras) -> dict:
    avisos = avisos_do_rascunho(pedido)
    contexto = {
        "pedido": pedido,
        "linhas": [(item, avisos.por_item.get(item.pk)) for item in pedido.itens.all()],
        "avisos": avisos,
        "erro_desconto": avisos.erro_desconto,
        "valor_desconto": None,  # None: o campo mostra o desconto gravado
        "novo_item": NovoItem(),
    }
    contexto.update(extras)
    return contexto


def _atualizacao(request, pedido: Pedido, *, parte_desconto: str | None = "form", **extras):
    """Responde a uma ação do editor com o pedaço "atualizacao", lido do banco depois dela.

    `parte_desconto`: "form" redesenha o formulário do desconto inteiro; "campo", só o campo do
    valor e o erro (resposta do próprio desconto); None, nada dele.
    """
    pedido = get_object_or_404(Pedido.objects.select_related("cliente"), pk=pedido.pk)
    contexto = _contexto_do_editor(pedido, parte_desconto=parte_desconto, **extras)
    return render(request, "pedidos/editor.html#atualizacao", contexto)


@require_POST
def novo(request):
    pedido = services.criar_rascunho(request.user)
    return redirecionar(request, reverse("pedidos:editar", args=[pedido.pk]))


@require_GET
def editar(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related("cliente"), pk=pk)
    if not pode_editar(pedido, request.user):
        messages.error(request, _motivo_sem_edicao(pedido))
        return redirect("pedidos:detalhe", pk=pk)
    # O foco começa na busca do cliente; com o cliente já escolhido, na do produto.
    if pedido.cliente_id is None:
        contexto = _contexto_do_editor(pedido, foco_cliente=True)
    else:
        contexto = _contexto_do_editor(pedido, novo_item=NovoItem(foco="produto"))
    return render(request, "pedidos/editor.html", contexto)


@require_GET
def sugestoes_cliente(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    busca = normalizar_busca(request.GET.get("q", ""))
    clientes = list(buscar_clientes(busca, limite=LIMITE_SUGESTOES)) if busca else []
    contexto = {"pedido": pedido, "busca": busca, "clientes": clientes}
    return render(request, "pedidos/editor.html#sugestoes_cliente", contexto)


@require_GET
def sugestoes_produto(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    busca = normalizar_busca(request.GET.get("q", ""))
    sugestoes = []
    if busca:
        no_pedido = dict(pedido.itens.values_list("produto_id", "quantidade"))
        sugestoes = [
            ProdutoSugerido(produto, no_pedido.get(produto.pk, 0))
            for produto in buscar_produtos(busca, limite=LIMITE_SUGESTOES)
        ]
    contexto = {"pedido": pedido, "busca": busca, "sugestoes": sugestoes}
    return render(request, "pedidos/editor.html#sugestoes_produto", contexto)


@require_POST
@_no_rascunho
def definir_cliente(request, pedido):
    form = ClienteForm(request.POST)
    if not form.is_valid():
        return _atualizacao(request, pedido, msg_cliente=MSG_ESCOLHA_CLIENTE)
    try:
        services.definir_cliente(pedido.pk, form.cleaned_data["cliente_id"], request.user)
    except Cliente.DoesNotExist:
        return _atualizacao(request, pedido, msg_cliente=MSG_ESCOLHA_CLIENTE)
    except RegraDeNegocio as erro:
        return _atualizacao(request, pedido, msg_cliente=erro.mensagem)
    # O cartão passa a mostrar o cliente, e o foco vai para a busca de produto. O formulário do
    # item não é redesenhado: a pessoa pode já estar digitando nele.
    resposta = _atualizacao(request, pedido, parte_cliente=True)
    resposta["HX-Trigger-After-Settle"] = json.dumps({"focar": "busca-produto"})
    return resposta


@require_POST
@_no_rascunho
def adicionar_item(request, pedido):
    """Dando certo, o formulário do item volta limpo, com o foco na busca de produto."""
    form = ItemForm(request.POST)
    if not form.is_valid():
        campo = "produto" if "produto_id" in form.errors else "quantidade"
        erro = form.errors["produto_id" if campo == "produto" else "quantidade"][0]
        return _item_com_erro(request, pedido, form, erro, campo)
    dados = form.cleaned_data
    try:
        item = services.adicionar_item(
            pedido.pk, dados["produto_id"], dados["quantidade"], request.user
        )
    except Produto.DoesNotExist:
        return _item_com_erro(request, pedido, form, MSG_ESCOLHA_PRODUTO, "produto")
    except RegraDeNegocio as erro:
        na_quantidade = isinstance(erro, EstoqueInsuficiente) or (
            erro.mensagem == MSG_QUANTIDADE_MAXIMA
        )
        campo = "quantidade" if na_quantidade else "produto"
        return _item_com_erro(request, pedido, form, erro.mensagem, campo)
    return _atualizacao(
        request, pedido, parte_item=True, destaque_id=item.pk, novo_item=NovoItem(foco="produto")
    )


def _item_com_erro(request, pedido: Pedido, form: ItemForm, mensagem: str, campo: str):
    """O formulário do item volta como estava, com a mensagem e o campo marcado.

    Com erro na quantidade, o produto escolhido continua valendo (e a linha de informação dele
    continua na tela). Com erro no produto, é preciso escolher outro: o texto do campo só fica se
    era uma busca (sem produto escolhido), para a lista de sugestões reabrir com ela.
    """
    escolhido = request.POST.get("produto_id", "")
    produto, no_pedido = None, 0
    if campo == "quantidade":
        produto = Produto.objects.filter(pk=form.cleaned_data["produto_id"]).first()
        item = pedido.itens.filter(produto=produto).first() if produto else None
        no_pedido = item.quantidade if item else 0
    novo_item = NovoItem(
        busca=request.POST.get("q", "") if produto or not escolhido else "",
        produto_id=escolhido if produto else "",
        quantidade=request.POST.get("quantidade", ""),
        campo_com_erro=campo,
        foco=campo,
        produto=produto,
        no_pedido=no_pedido,
    )
    return _atualizacao(request, pedido, parte_item=True, msg_produto=mensagem, novo_item=novo_item)


_PASSOS = {"mais": 1, "menos": -1}


@require_POST
@_no_rascunho
def alterar_quantidade(request, pedido, item_id):
    """Botões − e + da linha (acao=menos|mais) ou a quantidade digitada (quantidade)."""
    acao = request.POST.get("acao")
    try:
        if acao in _PASSOS:
            services.mudar_quantidade(pedido.pk, item_id, _PASSOS[acao], request.user)
        else:
            form = QuantidadeForm(request.POST)
            if not form.is_valid():
                return _atualizacao(request, pedido, msg_produto=form.errors["quantidade"][0])
            services.alterar_quantidade(
                pedido.pk, item_id, form.cleaned_data["quantidade"], request.user
            )
    except RegraDeNegocio as erro:
        return _atualizacao(request, pedido, msg_produto=erro.mensagem)
    return _atualizacao(request, pedido, destaque_id=item_id)


@require_POST
@_no_rascunho
def remover_item(request, pedido, item_id):
    try:
        services.remover_item(pedido.pk, item_id, request.user)
    except RegraDeNegocio as erro:
        return _atualizacao(request, pedido, msg_produto=erro.mensagem)
    return _atualizacao(request, pedido)


def _gravar_desconto(request, pedido: Pedido) -> str | None:
    """Grava o desconto enviado (tipo e valor) e devolve a mensagem de erro, se ele não vale."""
    form = DescontoForm(request.POST)
    if not form.is_valid():
        return next(iter(form.errors.values()))[0]
    try:
        services.definir_desconto(
            pedido.pk, form.cleaned_data["tipo"], form.cleaned_data["valor"], request.user
        )
    except RegraDeNegocio as erro:
        return erro.mensagem
    return None


def _desconto_recusado(request, pedido: Pedido, erro: str, **extras):
    """O campo do desconto volta com o que foi digitado, marcado, e a mensagem embaixo."""
    return _atualizacao(
        request,
        pedido,
        parte_desconto="campo",
        erro_desconto=erro,
        valor_desconto=request.POST.get("valor", ""),
        **extras,
    )


@require_POST
@_no_rascunho
def definir_desconto(request, pedido):
    """A resposta redesenha só o campo do valor (com o erro, se houver), não o tipo: um clique em
    R$ ou % feito enquanto ela vinha continua valendo e é enviado em seguida."""
    erro = _gravar_desconto(request, pedido)
    if erro:
        return _desconto_recusado(request, pedido, erro)
    return _atualizacao(request, pedido, parte_desconto="campo")


@require_POST
@_no_rascunho
def definir_observacoes(request, pedido):
    """Gravadas enquanto se digita: a resposta não redesenha nenhum campo de digitação."""
    try:
        services.definir_observacoes(pedido.pk, request.POST.get("texto", ""), request.user)
    except RegraDeNegocio as erro:
        return avisar(_atualizacao(request, pedido, parte_desconto=None), erro.mensagem, "erro")
    return _atualizacao(request, pedido, parte_desconto=None)


@require_POST
@_no_rascunho
def confirmar(request, pedido):
    """Confirma com o que está na tela (Ruling R24).

    Os botões mandam junto as observações e o desconto dos campos (hx-include), que são gravados
    antes, pelos mesmos serviços: o pedido não é confirmado com um desconto diferente do que a
    pessoa vê. Desconto inválido ou recusado não confirma: o campo volta com o erro e o foco.
    """
    if "texto" in request.POST:
        try:
            services.definir_observacoes(pedido.pk, request.POST["texto"], request.user)
        except RegraDeNegocio as erro:
            resposta = _atualizacao(request, pedido, parte_desconto=None)
            return avisar(resposta, erro.mensagem, "erro")
    if "tipo" in request.POST or "valor" in request.POST:
        erro = _gravar_desconto(request, pedido)
        if erro:
            return _desconto_recusado(request, pedido, erro, foco_desconto=True)
    try:
        confirmado = services.confirmar_pedido(pedido.pk, request.user)
    except services.PrecosAlterados as erro:
        return _atualizacao(request, pedido, mudancas=erro.mudancas)
    except services.ConfirmacaoRecusada as erro:
        return _atualizacao(request, pedido, motivos=erro.motivos)
    except RegraDeNegocio as erro:  # deixou de ser rascunho no meio do caminho
        return _voltar_ao_detalhe(request, pedido, erro.mensagem)
    messages.success(request, f"Pedido {numero_pedido(confirmado.numero)} confirmado")
    return redirecionar(request, reverse("pedidos:detalhe", args=[pedido.pk]))


@require_POST
@_no_rascunho
def excluir(request, pedido):
    try:
        services.excluir_rascunho(pedido.pk, request.user)
    except RegraDeNegocio as erro:
        return _voltar_ao_detalhe(request, pedido, erro.mensagem)
    messages.success(request, "Rascunho excluído.")
    return redirecionar(request, reverse("pedidos:lista"))
