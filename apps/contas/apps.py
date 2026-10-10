from django.apps import AppConfig


class ContasConfig(AppConfig):
    name = "apps.contas"
    verbose_name = "Contas"

    def ready(self):
        from . import sinais  # noqa: F401  (liga os receptores do registro de acessos)
        from .totp import instalar

        instalar()
