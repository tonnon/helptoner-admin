from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from apps.contas.models import Usuario
from apps.contas.services import gerar_senha_temporaria


class Command(BaseCommand):
    help = (
        "Cria o primeiro administrador (superusuário, com acesso ao painel de manutenção) e "
        "mostra a senha temporária. No primeiro acesso, ele troca a senha e configura a "
        "verificação em duas etapas. Os demais funcionários são criados na tela Funcionários."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="e-mail de login")
        parser.add_argument("--nome", required=True, help="nome completo")

    def handle(self, *args, email, nome, **opcoes):
        email = email.strip().lower()
        nome = nome.strip()
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError(f"E-mail inválido: {email!r}.") from None
        if not nome:
            raise CommandError("Informe o nome com --nome.")
        if Usuario.objects.filter(email=email).exists():
            raise CommandError(f"Já existe um usuário com o e-mail {email}.")
        senha = gerar_senha_temporaria()
        with transaction.atomic():
            # create_superuser já põe no grupo Administrador; deve_trocar_senha começa True.
            usuario = Usuario.objects.create_superuser(email, nome, senha)
        self.stdout.write(f"Administrador criado: {usuario.nome} <{usuario.email}>")
        self.stdout.write(f"Senha temporária: {senha}")
        self.stdout.write(
            "Repasse a senha com cuidado: ela não fica gravada e não será mostrada de novo."
        )
