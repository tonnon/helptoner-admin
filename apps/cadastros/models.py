from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from .documentos import normalizar_documento, validar_documento


class TipoPessoa(models.TextChoices):
    PF = "PF", "Pessoa"
    PJ = "PJ", "Empresa"


SIGLAS_UF = (
    "AC",
    "AL",
    "AP",
    "AM",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MT",
    "MS",
    "MG",
    "PA",
    "PB",
    "PR",
    "PE",
    "PI",
    "RJ",
    "RN",
    "RS",
    "RO",
    "RR",
    "SC",
    "SP",
    "SE",
    "TO",
)
UFS = [(sigla, sigla) for sigla in SIGLAS_UF]


class Cliente(models.Model):
    tipo = models.CharField("Tipo", max_length=2, choices=TipoPessoa, default=TipoPessoa.PJ)
    nome = models.CharField("Nome", max_length=200)
    documento = models.CharField("CPF/CNPJ", max_length=14, unique=True)
    telefone = models.CharField("Telefone", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)
    cep = models.CharField("CEP", max_length=8, blank=True)
    logradouro = models.CharField("Logradouro", max_length=200, blank=True)
    numero = models.CharField("Número", max_length=20, blank=True)
    complemento = models.CharField("Complemento", max_length=100, blank=True)
    bairro = models.CharField("Bairro", max_length=100, blank=True)
    cidade = models.CharField("Cidade", max_length=100, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UFS, blank=True)
    observacoes = models.TextField("Observações", blank=True)
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    history = HistoricalRecords(excluded_fields=["atualizado_em"])

    class Meta:
        ordering = ["nome"]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self):
        return self.nome

    @property
    def codigo(self) -> int:
        return self.pk

    def clean(self):
        erros = {}
        if self.documento:
            try:
                self.documento = validar_documento(self.tipo, self.documento)
            except ValidationError as erro:
                erros["documento"] = erro.messages
        if self.cep:
            self.cep = normalizar_documento(self.cep)
            if not (len(self.cep) == 8 and self.cep.isdigit()):
                erros["cep"] = "CEP inválido: informe os 8 dígitos."
        if erros:
            raise ValidationError(erros)


CAMPOS_DOS_MOVIMENTOS = frozenset({"estoque", "custo_medio"})


class Produto(models.Model):
    codigo = models.CharField(
        "Código",
        max_length=30,
        unique=True,
        error_messages={"unique": "Já existe um produto com este código."},
    )
    descricao = models.CharField("Descrição", max_length=200)
    marca = models.CharField("Marca", max_length=60)
    preco = models.DecimalField("Preço", max_digits=12, decimal_places=2)
    # Só os movimentos de estoque (Tarefa 12) mudam estes dois campos.
    custo_medio = models.DecimalField(
        "Custo médio", max_digits=14, decimal_places=4, default=0, editable=False
    )
    estoque = models.IntegerField("Estoque", default=0, editable=False)
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    history = HistoricalRecords(excluded_fields=["estoque", "custo_medio", "atualizado_em"])

    class Meta:
        ordering = ["codigo"]
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(estoque__gte=0), name="produto_estoque_nao_negativo"
            ),
            models.CheckConstraint(
                condition=models.Q(preco__gte=0), name="produto_preco_nao_negativo"
            ),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.descricao}"

    def save(self, *args, **kwargs):
        self.codigo = (self.codigo or "").strip().upper()
        if (
            not self._state.adding
            and kwargs.get("update_fields") is None
            and not kwargs.get("force_insert")
        ):
            # Um save() completo (formulário, painel de manutenção) regravaria o estoque e o custo
            # lidos quando a instância foi carregada e desfaria um movimento feito nesse meio
            # tempo. Esses dois só são gravados pelos movimentos (update() em estoque/services.py).
            adiados = self.get_deferred_fields()
            kwargs["update_fields"] = [
                campo.name
                for campo in self._meta.concrete_fields
                if not campo.primary_key
                and campo.name not in CAMPOS_DOS_MOVIMENTOS
                and campo.attname not in adiados
            ]
        super().save(*args, **kwargs)
