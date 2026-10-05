from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, Group, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

ADMINISTRADOR = "Administrador"
VENDEDOR = "Vendedor"
PERFIS = (ADMINISTRADOR, VENDEDOR)


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _criar(self, email, nome, password, **extra):
        if not email or not email.strip():
            raise ValueError("O e-mail é obrigatório.")
        usuario = self.model(email=self.normalize_email(email.strip()).lower(), nome=nome, **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, nome, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._criar(email, nome, password, **extra)

    def create_superuser(self, email, nome, password, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("O superusuário precisa de is_staff=True e is_superuser=True.")
        usuario = self._criar(email, nome, password, **extra)
        usuario.groups.add(Group.objects.get_or_create(name=ADMINISTRADOR)[0])
        return usuario


class Usuario(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("e-mail", unique=True)
    nome = models.CharField("nome", max_length=150)
    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("acesso ao painel de manutenção", default=False)
    deve_trocar_senha = models.BooleanField("deve trocar a senha", default=True)
    codigos_recuperacao_entregues = models.BooleanField(
        "códigos de recuperação entregues", default=False
    )
    criado_em = models.DateTimeField("criado em", default=timezone.now)

    objects = UsuarioManager()
    history = HistoricalRecords(excluded_fields=["password", "last_login"])

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.nome or self.email

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    @cached_property
    def _nomes_dos_grupos(self) -> frozenset[str]:
        return frozenset(self.groups.values_list("name", flat=True))

    @property
    def eh_administrador(self) -> bool:
        return ADMINISTRADOR in self._nomes_dos_grupos

    @property
    def perfil(self) -> str:
        if self.eh_administrador:
            return ADMINISTRADOR
        if VENDEDOR in self._nomes_dos_grupos:
            return VENDEDOR
        return ""

    @property
    def primeiro_nome(self) -> str:
        partes = self.nome.split()
        return partes[0] if partes else ""


class RegistroAcesso(models.Model):
    """Uma tentativa de login, com ou sem sucesso (gravada por apps.contas.sinais)."""

    email_tentado = models.CharField("e-mail tentado", max_length=254)
    usuario = models.ForeignKey(
        Usuario,
        verbose_name="usuário",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acessos",
    )
    sucesso = models.BooleanField("sucesso")
    motivo = models.CharField("motivo", max_length=100, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    navegador = models.CharField("navegador", max_length=300, blank=True)
    quando = models.DateTimeField("quando", default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "registro de acesso"
        verbose_name_plural = "registros de acesso"
        ordering = ["-quando"]

    def __str__(self):
        situacao = "entrou" if self.sucesso else "recusado"
        return f"{self.email_tentado} ({situacao})"
