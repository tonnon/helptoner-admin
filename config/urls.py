from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
]

handler403 = "apps.core.views.erro_403"
handler404 = "apps.core.views.erro_404"
handler500 = "apps.core.views.erro_500"
