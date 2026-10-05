from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import NovaSenhaForm
from .middleware import ETAPA_CODIGOS, ETAPA_SENHA, etapa_do_primeiro_acesso


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
