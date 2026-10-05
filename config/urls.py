from django.urls import include, path, re_path

from apps.core.views import rota_bloqueada

urlpatterns = [
    # Partes do allauth que o sistema não usa: sem cadastro público, sem e-mail (nem troca, nem
    # confirmação, nem "esqueci a senha"), sem login por código e sem desligar o próprio 2FA.
    # Respondem 404 antes de chegar ao allauth.
    re_path(
        r"^contas/(signup|email|confirm-email|password/(set|reset)|login/code"
        r"|2fa/totp/deactivate)(/.*)?$",
        rota_bloqueada,
    ),
    path("contas/", include("allauth.urls")),
    path("", include("apps.core.urls")),
]

handler403 = "apps.core.views.erro_403"
handler404 = "apps.core.views.erro_404"
handler500 = "apps.core.views.erro_500"
