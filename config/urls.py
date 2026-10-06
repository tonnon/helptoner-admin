from functools import wraps

from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.urls import include, path, re_path

from apps.core.permissoes import eh_administrador
from apps.core.views import rota_bloqueada


def _sem_formulario_de_login(login):
    """O formulário de login do Django entra sem a verificação em duas etapas: nunca é usado.

    O secure_admin_login já manda quem não entrou para o login do sistema e recusa quem não é
    is_staff. Daqui em diante, só o GET de quem pode usar o painel passa, e o login do Django
    apenas redireciona para o painel. O resto (ex.: is_staff sem ser superusuário, ou um POST
    com a senha de outra pessoa) recebe 403.
    """

    @wraps(login)
    def view(request, *args, **kwargs):
        if request.method != "GET" or not admin.site.has_permission(request):
            raise PermissionDenied
        return login(request, *args, **kwargs)

    return view


# Painel de manutenção: endereço não padrão, só para o superusuário que também tem o perfil
# Administrador, pelo mesmo login do sistema (com a verificação em duas etapas e o primeiro
# acesso obrigatório).
admin.site.has_permission = lambda r: (
    r.user.is_active and r.user.is_superuser and eh_administrador(r.user)
)
admin.site.login = secure_admin_login(_sem_formulario_de_login(admin.site.login))

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    # Partes do allauth que o sistema não usa: sem cadastro público, sem e-mail (nem troca, nem
    # confirmação, nem "esqueci a senha"), sem login por código e sem desligar o próprio 2FA.
    # Respondem 404 antes de chegar ao allauth.
    re_path(
        r"^contas/(signup|email|confirm-email|password/(set|reset)|login/code"
        r"|2fa/totp/deactivate)(/.*)?$",
        rota_bloqueada,
    ),
    path("contas/", include("allauth.urls")),
    path("", include("apps.contas.urls")),
    path("", include("apps.cadastros.urls")),
    path("", include("apps.estoque.urls")),
    path("", include("apps.pedidos.urls")),
    path("", include("apps.core.urls")),
]

handler403 = "apps.core.views.erro_403"
handler404 = "apps.core.views.erro_404"
handler500 = "apps.core.views.erro_500"
