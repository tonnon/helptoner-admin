from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.erros import RegraDeNegocio
from apps.core.htmx import eh_htmx
from apps.core.permissoes import requer_administrador

from .forms import FuncionarioForm, NovaSenhaForm, NovoFuncionarioForm
from .models import Usuario
from .services import (
    ETAPA_CODIGOS,
    ETAPA_SENHA,
    alterar_funcionario,
    criar_funcionario,
    desativar_funcionario,
    etapa_do_primeiro_acesso,
    redefinir_senha,
    zerar_2fa,
)


@require_http_methods(["GET", "POST"])
def primeiro_acesso_senha(request):
    """Etapa 1: troca da senha temporária (sem pedir a atual, que a pessoa acabou de digitar)."""
    usuario = request.user
    if etapa_do_primeiro_acesso(usuario) != ETAPA_SENHA:
        return redirect("core:inicio")  # quem já trocou usa "Trocar senha", que pede a atual
    form = NovaSenhaForm(usuario, request.POST if request.method == "POST" else None)
    if form.is_valid():
        form.save()
        update_session_auth_hash(request, usuario)
        return redirect("core:inicio")  # o PrimeiroAcessoMiddleware leva à próxima etapa
    return render(request, "contas/primeiro_acesso_senha.html", {"form": form})


@require_POST
def primeiro_acesso_concluir(request):
    """Fim da etapa 3: a pessoa guardou os códigos de recuperação."""
    usuario = request.user
    if etapa_do_primeiro_acesso(usuario) == ETAPA_CODIGOS:  # só com o autenticador ativo
        usuario.codigos_recuperacao_entregues = True
        usuario.save(update_fields=["codigos_recuperacao_entregues"])
        messages.success(request, "Tudo pronto! Seu acesso está configurado.")
    return redirect("core:inicio")


@require_GET
def minha_conta(request):
    return render(request, "contas/minha_conta.html")


# ---------- Funcionários (só o Administrador) ----------
# @requer_administrador fica por fora de tudo: o Vendedor recebe 403 antes de qualquer consulta.


@requer_administrador
@require_GET
def funcionarios(request):
    """Lista (padrão P18): a página abre com o esqueleto e busca as linhas por HTMX."""
    if not eh_htmx(request):
        return render(request, "contas/funcionarios.html")
    lista = Usuario.objects.prefetch_related("groups").order_by("-is_active", "nome")
    return render(request, "contas/funcionarios.html#resultados", {"funcionarios": lista})


def _mostrar_senha_temporaria(request, funcionario, senha, *, novo):
    """Mostra a senha uma única vez: ela não é gravada e a resposta não fica em cache."""
    resposta = render(
        request,
        "contas/senha_temporaria.html",
        {"funcionario": funcionario, "senha": senha, "novo": novo},
    )
    add_never_cache_headers(resposta)
    return resposta


@requer_administrador
@require_http_methods(["GET", "POST"])
def funcionario_novo(request):
    form = NovoFuncionarioForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        try:
            funcionario, senha = criar_funcionario(**form.cleaned_data, por=request.user)
        except RegraDeNegocio as erro:  # e-mail repetido
            form.add_error("email", erro.mensagem)
        else:
            return _mostrar_senha_temporaria(request, funcionario, senha, novo=True)
    return render(request, "contas/funcionario_form.html", {"form": form})


@requer_administrador
@require_http_methods(["GET", "POST"])
def funcionario_editar(request, pk):
    funcionario = get_object_or_404(Usuario, pk=pk)
    form = FuncionarioForm(
        request.POST if request.method == "POST" else None,
        initial={"nome": funcionario.nome, "perfil": funcionario.perfil},
        travar_perfil=funcionario.pk == request.user.pk,
    )
    if form.is_valid():
        try:
            alterar_funcionario(funcionario, **form.cleaned_data, por=request.user)
        except RegraDeNegocio as erro:  # ex.: o próprio perfil, se o campo travado for burlado
            form.add_error("perfil", erro.mensagem)
        else:
            messages.success(request, "Funcionário salvo.")
            return redirect("contas:funcionarios")
    return render(
        request, "contas/funcionario_form.html", {"form": form, "funcionario": funcionario}
    )


@requer_administrador
@require_POST
def funcionario_redefinir_senha(request, pk):
    funcionario = get_object_or_404(Usuario, pk=pk)
    senha = redefinir_senha(funcionario, por=request.user)
    return _mostrar_senha_temporaria(request, funcionario, senha, novo=False)


@requer_administrador
@require_POST
def funcionario_zerar_2fa(request, pk):
    funcionario = get_object_or_404(Usuario, pk=pk)
    zerar_2fa(funcionario, por=request.user)
    messages.success(request, "Verificação em duas etapas zerada.")
    return redirect("contas:funcionario_editar", pk=pk)


@requer_administrador
@require_POST
def funcionario_desativar(request, pk):
    funcionario = get_object_or_404(Usuario, pk=pk)
    try:
        desativar_funcionario(funcionario, por=request.user)
    except RegraDeNegocio as erro:  # a si mesmo
        messages.error(request, erro.mensagem)
        return redirect("contas:funcionario_editar", pk=pk)
    messages.success(request, "Funcionário desativado.")
    return redirect("contas:funcionarios")
