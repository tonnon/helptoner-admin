# Sistema de Pedidos Helptoner: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o sistema web de pedidos de venda da Helptoner descrito na especificação, do repositório vazio até a publicação na Vercel, em 8 etapas que terminam com algo funcionando e testado.

**Architecture:** O Django 6.1 monta as telas no servidor e o HTMX troca só pedaços da página (template partials do Django 6). As regras de negócio ficam em `services.py` (e em funções puras como `calculos.py`), com transações e travas de linha no PostgreSQL; as views só leem a entrada, chamam o serviço e escolhem a resposta. Em produção, tudo roda numa única função Python da Vercel (gru1), com o banco no Neon (São Paulo), sem gravar nada em disco.

**Tech Stack:** Python 3.14, Django 6.1, PostgreSQL 18 (Neon), HTMX 2.0.x, Tailwind CSS 4 (executável standalone), django-allauth com `mfa`, argon2-cffi, django-simple-history, fpdf2, openpyxl, WhiteNoise, sentry-sdk, uv, pytest + pytest-django, Playwright (pytest-playwright), pypdf (só nos testes), ruff, pip-audit.

**Spec:** `docs/superpowers/specs/2026-10-02-helptoner-pedidos-design.md`. Referências como "§3.2" apontam para as seções dela. Os esboços aprovados (`docs/esbocos/`) são a referência visual de cada tela.

## Global Constraints

- Python 3.14 (`requires-python = ">=3.14,<3.15"`), Django `>=6.1,<6.2`, PostgreSQL 18. Versões fixadas no `uv.lock`; pacote novo só com `uv add`.
- Custo zero. Em produção, nenhum arquivo vem de site de terceiros: HTMX, fonte Inter, logo e CSS são servidos pelo próprio sistema.
- Textos de tela e mensagens em português do Brasil. Nomes de código em português, como na especificação (`Pedido`, `confirmar_pedido`, `services.py`). Campos de modelo com `verbose_name` em português, porque aparecem nos formulários e no histórico.
- Dinheiro sempre em `Decimal`, nunca `float`. Arredondamento `ROUND_HALF_UP`, com 2 casas em valores e 4 no custo (§3.3, §3.5). Somas em SQL são exatas e o arredondamento final é feito em Python.
- Datas gravadas em UTC e exibidas no fuso `America/Sao_Paulo` (`TIME_ZONE = "America/Sao_Paulo"`, `USE_TZ = True`). Dia, semana e mês são sempre os de Brasília.
- Permissões conferidas no servidor, em cada view e em cada serviço (§4.1). Esconder botão é só conforto visual.
- CSP sem `unsafe-inline` e sem `unsafe-eval`. Nos templates, não usar `<script>` sem `src`, atributo `style=`, atributos `on*=`, `hx-on` nem `javascript:`. No JS próprio, não usar `eval`, `new Function`, `innerHTML`, `outerHTML`, `insertAdjacentHTML` nem `setAttribute("style", …)`; usar classes, `textContent` e criação de elementos. O HTMX roda com `allowEval: false` e `includeIndicatorStyles: false`.
- Regras de negócio só em `apps/<app>/services.py` (ou em módulos puros como `calculos.py` e `documentos.py`). As views não decidem regra.
- Os testes rodam no PostgreSQL (local: PostgreSQL 18 no Windows; CI: imagem `postgres:18`). TDD: primeiro o teste falhando, depois o código.
- PDF e Excel são gerados na memória; nada é gravado em disco em produção.
- Segredos só em variáveis de ambiente (Vercel e GitHub Actions). O `.env.local` nunca vai para o Git (o `.gitignore` já cobre `.env.*`).
- Commits com a identidade pessoal já configurada neste repositório (`lucastonnon`), mensagens no formato `tipo: descrição em português` (como os commits existentes) e **sem** linha `Co-Authored-By` nem qualquer menção ao Claude.
- Os comandos do plano são `uv run …` e funcionam igual no PowerShell e no bash.

## Review Focus

1. **Sessão expirada no meio de uma ação HTMX** (§8). A tela de login não pode aparecer enfiada dentro de um pedaço da página: o navegador vai inteiro para o login e, depois de entrar, volta para a página em que a pessoa estava (por exemplo, o rascunho). Testes nas Tarefas 3 (caso genérico) e 19 (rascunho).
2. **Clique duplo ou duas abas no mesmo pedido.** Confirmar ou cancelar o mesmo pedido duas vezes ao mesmo tempo só pode valer uma vez: um número, uma baixa, uma devolução. Adicionar o mesmo produto ao mesmo rascunho em duas abas soma na linha, sem erro 500. Testes nas Tarefas 15, 16 e 17.
3. **Bordas do fuso de Brasília.** Um pedido confirmado em 31/10 às 22h30 (já 01/11 em UTC) conta em outubro no Início, no filtro de mês da lista, nos relatórios e no "último pedido" do cliente. Os agrupamentos por dia, semana e mês usam o fuso de Brasília. Testes nas Tarefas 18, 21 e 24.
4. **Desconto em R$ que passa a ser maior que o subtotal** depois de remover um item, diminuir uma quantidade ou atualizar um preço na confirmação. O campo mostra "O desconto não pode passar do subtotal.", o total aparece sem o desconto e a confirmação é recusada. Desconto de 100% ou receita zero não pode causar divisão por zero na margem. Testes nas Tarefas 14, 15, 16 e 19.
5. **Busca do jeito que as pessoas digitam.** "joao" acha "João", "123.456" acha o CPF 123.456.789-09, "ce285" acha "CE285A", "tn1060" acha "TN-1060", "1.042" acha o pedido nº 1.042, e caracteres como `%`, `_`, `'` e `\` não quebram nada. Testes nas Tarefas 10, 11 e 18.

## Decisões tomadas neste plano

Pontos que a especificação não fixava ou que mudaram depois dela. Cada um tem teste na tarefa indicada.

| # | Decisão | Tarefa |
|---|---|---|
| P1 | **CNPJ alfanumérico.** Desde julho de 2026, a Receita emite CNPJ com letras (IN RFB 2.229/2024). O documento é guardado sem máscara e em maiúsculas: 11 dígitos (CPF) ou 14 caracteres (CNPJ, sendo 12 letras ou números e 2 dígitos verificadores). No cálculo do dígito verificador, cada caractere vale o código ASCII menos 48. Isso ajusta o "só com os dígitos" de §3.7. | 9 |
| P2 | Adicionar ao rascunho mais do que o estoque disponível é recusado com a mensagem do esboço ("dá para adicionar mais N"). Se o estoque cair depois, a linha mostra um aviso e a confirmação é recusada (§3.2). | 15 |
| P3 | Desconto maior que o subtotal: o valor digitado fica salvo no rascunho, o campo mostra o erro, o total ignora o desconto e a confirmação é recusada, como no esboço. Com subtotal zero, não há erro e o desconto vale zero. | 14 |
| P4 | O desconto é dividido entre os itens por arredondamento acumulado. A soma sempre fecha com o desconto, e nenhum item fica com parte negativa ou maior que o próprio total. Os centavos de diferença ficam nos últimos itens. | 14 |
| P5 | "Quem emitiu" é quem criou o rascunho (`criado_por`). Vale para a lista, para os números do Início do Vendedor e para os relatórios. | 15 |
| P6 | Um rascunho pode ser editado, confirmado e excluído por quem o criou ou por um Administrador. | 15 |
| P7 | "Repetir pedido" copia o cliente e os itens, com código, descrição e preço atuais. Não copia desconto nem observações. Itens inativos ou sem estoque entram com aviso. | 17 |
| P8 | O código do cliente é o `id` gerado pelo banco. | 10 |
| P9 | Clientes e produtos inativados podem ser reativados, por quem pode editá-los. | 10, 11 |
| P10 | O custo unitário da entrada e do estoque inicial precisa ser maior que zero. A entrada exige observação e o ajuste exige motivo. O ajuste tem dois tipos (`ajuste_mais` e `ajuste_menos`), porque a quantidade do movimento é sempre maior que zero. | 12 |
| P11 | A quantidade por item é um inteiro de 1 a 9.999. | 15, 19 |
| P12 | O `RegistroAcesso` ganha o campo `motivo` (ex.: "E-mail ou senha incorretos", "Código de verificação inválido"), como no esboço do histórico. | 5 |
| P13 | Um Administrador não pode desativar a si mesmo nem mudar o próprio perfil. Assim, sempre sobra pelo menos um Administrador ativo. | 8 |
| P14 | Só pedido confirmado ou cancelado tem PDF, porque o rascunho não tem número. O PDF do cancelado sai marcado como "CANCELADO". | 20 |
| P15 | No Início, "Rascunhos em aberto" mostra os rascunhos da própria pessoa, e "Últimos pedidos" mostra os 5 últimos da empresa (todos podem ver todos os pedidos). | 21 |
| P16 | Os atalhos de período incluem o mês atual. "Últimos 3 meses" vai do dia 1º de dois meses atrás até hoje; "Últimos 12 meses", do dia 1º de onze meses atrás até hoje; "2026 até agora", de 01/01 até hoje. O período anterior é o mesmo intervalo deslocado 3, 12 e 12 meses para trás. Nas datas personalizadas, é o mesmo número de dias imediatamente antes. | 23 |
| P17 | O agrupamento por dia aceita períodos de no máximo 366 dias. | 23 |
| P18 | As listas (pedidos, clientes, produtos, estoque), o Início e os relatórios abrem com esqueleto e buscam os dados por HTMX (`hx-trigger="load"`). A mesma URL devolve só o pedaço `#resultados` quando a requisição é HTMX. | 4 |
| P19 | Em produção, as migrações rodam pelo botão "Publicar", com a conexão direta do Neon. Nas prévias, rodam no build da Vercel, só no banco de prévia. A tabela de cache do Django é criada por uma migração, para existir nos testes, na prévia e na produção. | 3, 28, 30 |
| P20 | O HTMX roda com `historyCacheSize: 0`, para não guardar páginas com dados de clientes no `localStorage` do navegador (LGPD). | 4 |
| P21 | Os testes no navegador (Playwright) rodam no GitHub Actions a cada envio, junto com os demais. | 29 |

## Mapa de arquivos

```
manage.py                    # settings padrão: config.settings.local
pyproject.toml, uv.lock, .python-version, vercel.json, .vercelignore, .env.exemplo
config/settings/             # base.py, local.py, teste.py, producao.py
config/urls.py, config/wsgi.py   # wsgi: settings padrão config.settings.producao
apps/core/        # erros, dinheiro, datas, formatacao, permissoes, htmx, middleware, contexto,
                  # pdf (+ pdf_recursos/), sentry, historico, views (saúde, início, erros)
apps/contas/      # Usuario, RegistroAcesso, services (funcionários), sinais, navegador, adapter,
                  # middleware (primeiro acesso), comando criar_primeiro_admin
apps/cadastros/   # documentos (CPF/CNPJ), Cliente, Produto, buscas
apps/estoque/     # MovimentoEstoque, services (movimentos e custo médio)
apps/pedidos/     # calculos (puros), Pedido/ItemPedido/ContadorPedido, services, consultas, pdf
apps/relatorios/  # periodos, tabelas, consultas, exportacao
templates/        # base.html, base_publica.html, componentes/, icones/, <app>/,
                  # account/, mfa/, allauth/ (sobrescritos do allauth), 403/404/429/500.html
static/           # css/app.css (gerado), js/{app,mascaras,sugestoes,graficos}.js,
                  # vendor/htmx.min.js, fontes/, img/
tailwind/app.css  # fonte do CSS
scripts/          # css.py (Tailwind), vercel_build.py
tests/            # conftest.py, apoio.py, core/, contas/, cadastros/, estoque/, pedidos/,
                  # relatorios/, seguranca/, e2e/
.github/          # workflows/{ci,publicar,backup,teste-restauracao}.yml, actions/backup/, dependabot.yml
docs/operacao.md
```

## Convenções de teste

- `uv run pytest` roda tudo menos os testes no navegador; `uv run pytest -m e2e` roda os testes no navegador.
- `tests/apoio.py` reúne fábricas e utilidades. Cada tarefa que cria um modelo acrescenta a sua fábrica ali, com a assinatura dada no bloco Interfaces.
- `tests/conftest.py` tem as fixtures `administrador` (Lucas Tonnon, `lucas@helptoner.com.br`) e `vendedor` (Carla Souza, `carla@helptoner.com.br`), que são usuários prontos (senha trocada, 2FA ativo e códigos entregues), e `client_admin` e `client_vendedor`, que são instâncias novas de `django.test.Client` já logadas com `force_login`.
- Requisição HTMX nos testes: `client.get(url, headers={"HX-Request": "true"})`.
- Listas centrais criadas na Tarefa 3 (e na 11) e aumentadas pelas tarefas seguintes:
  - `tests/seguranca/test_permissoes.py::ROTAS_SO_ADMIN`: lista de `(método, url)` que precisam devolver 403 para o Vendedor;
  - `tests/seguranca/test_login_obrigatorio.py::ROTAS_LIVRES`: nomes de URL que dispensam login, cada um com o motivo num comentário;
  - `tests/seguranca/test_sem_custo.py::PAGINAS`: páginas e pedaços HTMX em que o Vendedor nunca pode ver custo, lucro ou margem. As URLs podem ter `{produto}`, `{pedido}` e `{rascunho}`, preenchidos com os ids da fixture `cenario_custo`.
- Testes de concorrência usam `@pytest.mark.django_db(transaction=True)` e a utilidade `rodar_juntos` (Tarefa 15).
- Toda pasta dentro de `tests/` tem `__init__.py`, porque há arquivos de teste com o mesmo nome em pastas diferentes.
- Datas "de hoje" nos testes usam `apps.core.datas.hoje()` (Brasília), nunca `date.today()`.

---

## Etapa 1: Fundação

**Ao fim da etapa:** o projeto roda no Windows com PostgreSQL 18; os testes e o ruff passam; existe um usuário próprio com os perfis; todas as páginas exigem login e saem com os cabeçalhos de segurança; o layout já tem a identidade visual.

### Tarefa 1: Projeto, ambiente e página de saúde

**Files:**
- Create: `pyproject.toml`, `.python-version`, `manage.py`, `.env.exemplo`, `config/__init__.py`, `config/settings/__init__.py`, `config/settings/base.py`, `config/settings/local.py`, `config/settings/teste.py`, `config/settings/producao.py`, `config/urls.py`, `config/wsgi.py`, `apps/__init__.py`, `apps/core/__init__.py`, `apps/core/apps.py`, `apps/core/views.py`, `apps/core/urls.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/apoio.py`, `tests/core/test_saude.py`, `tests/seguranca/test_settings.py`
- Modify: `.gitignore` (acrescentar `.ferramentas/`, `staticfiles/`, `.pytest_cache/`, `.ruff_cache/`, `test-results/`)

**Interfaces:**
- Produces: `apps.core.views.saude(request) -> JsonResponse` em `/saude/`, com o nome `core:saude`. Em `tests/apoio.py`: `rodar_django(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]`, que roda `manage.py` com o Python atual, usando o `os.environ` sobreposto por `env`, e captura a saída como texto. Em `config/settings/base.py`: `banco_de_dados(url: str, **opcoes) -> dict`, que usa `dj_database_url.parse`.

- [ ] **Step 1: Preparar o computador** (uma vez só; pode precisar do Lucas, porque pede permissão de administrador do Windows)
  - `winget install --id astral-sh.uv -e` e, depois, `uv python install 3.14`.
  - PostgreSQL 18 pelo instalador oficial (EDB) ou com `winget install --id PostgreSQL.PostgreSQL.18 -e`. A extensão `unaccent` já vem junto.
  - No `psql`, como `postgres`: `CREATE ROLE helptoner LOGIN PASSWORD '<senha>' CREATEDB;` e `CREATE DATABASE helptoner OWNER helptoner;`.
  - Criar o `.env.local` (fora do Git) com `DATABASE_URL=postgres://helptoner:<senha>@localhost:5432/helptoner`.
  - Conferir: `uv run --python 3.14 python --version` mostra `Python 3.14.x`, e `psql -U helptoner -d helptoner -c "select version()"` mostra `PostgreSQL 18`.

- [ ] **Step 2: Criar o `pyproject.toml` e instalar**

```toml
[project]
name = "helptoner-pedidos"
version = "0.1.0"
requires-python = ">=3.14,<3.15"
dependencies = ["django>=6.1,<6.2", "psycopg[binary]>=3.3", "dj-database-url>=3.1"]

[dependency-groups]
dev = ["pytest>=8", "pytest-django>=4.14", "ruff>=0.16", "python-dotenv>=1.1"]

[tool.uv]
package = false

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.teste"
addopts = "-m 'not e2e'"
markers = ["e2e: testes no navegador (Playwright)"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "DJ", "S", "SIM"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106", "S311", "S603", "S607"]
"scripts/**" = ["S603", "S607", "S310"]
```

`.python-version` contém `3.14`. Rode `uv sync`.

- [ ] **Step 3: Escrever os testes que falham**

```python
# tests/core/test_saude.py (sem marcação de banco: qualquer consulta ao banco faz o teste falhar)
def test_saude_responde_sem_login_e_sem_banco(client):
    r = client.get("/saude/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

# tests/seguranca/test_settings.py
def test_local_recusa_rodar_na_vercel():
    r = rodar_django("check", env={"DJANGO_SETTINGS_MODULE": "config.settings.local", "VERCEL": "1"})
    assert r.returncode != 0 and "config.settings.local" in r.stderr

def test_producao_exige_chave_secreta():
    r = rodar_django("check", env={"DJANGO_SETTINGS_MODULE": "config.settings.producao",
                                   "DJANGO_SECRET_KEY": "", "DATABASE_URL": "postgres://u:p@localhost/x"})
    assert r.returncode != 0 and "DJANGO_SECRET_KEY" in r.stderr

def test_banco_de_teste_e_postgresql_18(db):
    from django.db import connection
    assert connection.vendor == "postgresql" and connection.pg_version >= 180000
```

- [ ] **Step 4: Rodar e ver falhar.** `uv run pytest`. Esperado: erros de import/URL (o projeto ainda não existe).

- [ ] **Step 5: Implementar**
  - `base.py`: `BASE_DIR`, apps do `django.contrib` + `apps.core`, middleware padrão do Django, `TEMPLATES` com `DIRS=[BASE_DIR / "templates"]`, `LANGUAGE_CODE = "pt-br"`, fuso de Brasília, `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`, `STATIC_URL = "/static/"`, `STATICFILES_DIRS = [BASE_DIR / "static"]`, `STATIC_ROOT = BASE_DIR / "staticfiles"`, `WSGI_APPLICATION = "config.wsgi.application"` (sem `ASGI_APPLICATION`, para a Vercel usar o WSGI). O `base.py` não lê `DATABASE_URL`; cada ambiente monta `DATABASES` com `banco_de_dados(...)`.
  - `local.py`: primeiro, se `os.environ.get("VERCEL")` existir, levanta `ImproperlyConfigured("config.settings.local não pode rodar na Vercel; defina DJANGO_SETTINGS_MODULE=config.settings.producao.")`. Depois `load_dotenv(BASE_DIR / ".env.local")`, `from .base import *`, `DEBUG = True`, uma `SECRET_KEY` fixa de desenvolvimento, `ALLOWED_HOSTS = ["localhost", "127.0.0.1"]` e o banco vindo de `DATABASE_URL`.
  - `teste.py`: `from .local import *`, mais `PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]` para os testes ficarem rápidos.
  - `producao.py`: `DEBUG = False`; `SECRET_KEY` vem de `DJANGO_SECRET_KEY`, e se estiver vazia levanta `ImproperlyConfigured("Defina DJANGO_SECRET_KEY.")`; `ALLOWED_HOSTS` vem de `DJANGO_ALLOWED_HOSTS` (separado por vírgula); banco com `conn_max_age=0`, `ssl_require=True` e `DISABLE_SERVER_SIDE_CURSORS=True`.
  - `manage.py` usa `config.settings.local` como padrão; `config/wsgi.py` usa `config.settings.producao`.
  - `saude`: `@login_not_required` e `@require_GET`. Devolve `{"status": "ok"}` e não toca em `request.user`, na sessão nem no banco.
  - `.env.exemplo`: lista todas as variáveis do sistema, com uma linha explicando cada uma e sem valores reais (`DATABASE_URL`, `DATABASE_URL_DIRETA`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_SETTINGS_MODULE`, `ADMIN_URL`, `SENTRY_DSN`). As tarefas seguintes acrescentam as que criarem.
  - **Não rode `migrate` no banco local antes da Tarefa 2**: o modelo de usuário próprio precisa existir antes da primeira migração.

- [ ] **Step 6: Rodar e ver passar.** `uv run pytest` passa; `uv run ruff check .` e `uv run ruff format --check .` saem limpos; `uv run python manage.py runserver` e a página http://localhost:8000/saude/ mostra `{"status": "ok"}`.

- [ ] **Step 7: Commit.** `git add -A` e `git commit -m "chore: projeto Django com uv, PostgreSQL e página de saúde"`

### Tarefa 2: Usuário próprio e perfis

**Files:**
- Create: `apps/contas/__init__.py`, `apps/contas/apps.py`, `apps/contas/models.py`, `apps/contas/admin.py`, `apps/contas/migrations/0001_initial.py` (gerada), `apps/contas/migrations/0002_perfis.py` (dados), `apps/core/permissoes.py`, `tests/contas/test_usuario.py`, `tests/core/test_permissoes.py`
- Modify: `config/settings/base.py`, `tests/apoio.py`, `tests/conftest.py`
- Run: `uv add argon2-cffi django-simple-history`

**Interfaces:**
- Produces:
  - `apps.contas.models.ADMINISTRADOR = "Administrador"`, `VENDEDOR = "Vendedor"`, `PERFIS = (ADMINISTRADOR, VENDEDOR)`.
  - `Usuario(AbstractBaseUser, PermissionsMixin)` com os campos `email` (único, gravado sem espaços e em minúsculas), `nome`, `is_active`, `is_staff`, `deve_trocar_senha` (padrão `True`), `codigos_recuperacao_entregues` (padrão `False`) e `criado_em`. `USERNAME_FIELD = "email"` e `REQUIRED_FIELDS = ["nome"]`. Propriedades: `eh_administrador -> bool`, `perfil -> str` ("Administrador", "Vendedor" ou ""), `primeiro_nome -> str`. Histórico: `history = HistoricalRecords(excluded_fields=["password", "last_login"])`.
  - `Usuario.objects.create_user(email, nome, password=None, **extra)` e `create_superuser(email, nome, password, **extra)`. O superusuário fica com `is_staff=True` e `is_superuser=True` e entra no grupo Administrador.
  - `apps.core.permissoes`: `eh_administrador(usuario) -> bool` (falso para anônimo), `exigir_administrador(usuario) -> None` (levanta `PermissionDenied`) e o decorator `requer_administrador(view)`.
  - `tests.apoio`: `SENHA_TESTE = "senha-de-teste-bem-longa"` e `criar_usuario(perfil=VENDEDOR, *, email=None, nome="Carla Souza", pronto=True, senha=SENHA_TESTE) -> Usuario`. Com `pronto=True`, o usuário fica com `deve_trocar_senha=False` e `codigos_recuperacao_entregues=True` (a Tarefa 5 acrescenta o 2FA). Sem `email`, gera um endereço único.
  - Fixtures `administrador`, `vendedor`, `client_admin` e `client_vendedor`, conforme as Convenções de teste.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_email_e_gravado_em_minusculas_e_e_unico(db):
    u = Usuario.objects.create_user(" Carla@HelpToner.com.br ", "Carla", "senha-forte-1234")
    assert u.email == "carla@helptoner.com.br"
    with pytest.raises(IntegrityError):
        Usuario.objects.create_user("CARLA@helptoner.com.br", "Outra", "senha-forte-1234")

def test_migracao_cria_os_dois_perfis(db):
    assert {"Administrador", "Vendedor"} <= set(Group.objects.values_list("name", flat=True))

def test_superusuario_e_administrador(db):
    u = Usuario.objects.create_superuser("lucas@helptoner.com.br", "Lucas Tonnon", "senha-forte-1234")
    assert u.is_staff and u.is_superuser and u.eh_administrador and u.perfil == "Administrador"
    assert u.primeiro_nome == "Lucas"

def test_senhas_usam_argon2():
    from config.settings import base
    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"

@pytest.mark.parametrize("senha,aceita", [
    ("curta123456", False),          # 11 caracteres
    ("password1234", False),         # senha comum
    ("123456789012", False),         # só números
    ("carla@helptoner", False),      # parecida com o e-mail
    ("toner-azul-de-março", True),
])
def test_regras_de_senha(db, senha, aceita):
    u = Usuario(email="carla@helptoner.com.br", nome="Carla Souza")
    if aceita:
        validate_password(senha, u)
    else:
        with pytest.raises(ValidationError):
            validate_password(senha, u)

def test_historico_do_usuario_nao_guarda_senha(db):
    campos = {f.name for f in Usuario.history.model._meta.fields}
    assert "password" not in campos and "last_login" not in campos

def test_requer_administrador(rf, administrador, vendedor):
    view = requer_administrador(lambda request: HttpResponse("ok"))
    req = rf.get("/")
    req.user = vendedor
    with pytest.raises(PermissionDenied):
        view(req)
    req.user = administrador
    assert view(req).status_code == 200
    assert eh_administrador(AnonymousUser()) is False
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/contas tests/core/test_permissoes.py`. Esperado: erro de import (`apps.contas` não existe).

- [ ] **Step 3: Implementar**
  - Em `base.py`: `AUTH_USER_MODEL = "contas.Usuario"`; acrescentar `simple_history` e `apps.contas` a `INSTALLED_APPS`; `PASSWORD_HASHERS` com Argon2 em primeiro e os padrões do Django depois; `AUTH_PASSWORD_VALIDATORS` com `UserAttributeSimilarityValidator` (`user_attributes=("email", "nome")`), `MinimumLengthValidator` (`min_length=12`), `CommonPasswordValidator` e `NumericPasswordValidator`.
  - `eh_administrador` consulta o grupo uma vez por instância (`cached_property`). A normalização do e-mail fica no `save()` e no manager.
  - Migração `0002_perfis`: `RunPython` que cria os grupos "Administrador" e "Vendedor" (o reverso não faz nada).
  - Registrar `Usuario` no admin com `SimpleHistoryAdmin`, com fieldsets de e-mail, nome, situação e grupos (o painel só é usado para manutenção, na Tarefa 8).
  - **Atenção:** o django-simple-history 3.13 ainda não declara suporte ao Django 6.1. Se os testes desta tarefa falharem por causa dele, pare e avise o Lucas antes de procurar alternativa.

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` passa. Depois, `uv run python manage.py migrate` no banco local (a primeira vez).

- [ ] **Step 5: Commit.** `git commit -m "feat: usuário com login por e-mail e perfis Administrador e Vendedor"`

### Tarefa 3: Login obrigatório, cabeçalhos de segurança e páginas de erro

**Files:**
- Create: `apps/core/erros.py`, `apps/core/htmx.py`, `apps/core/middleware.py`, `apps/core/migrations/__init__.py`, `apps/core/migrations/0001_tabela_cache.py`, `templates/base_publica.html` (simples por enquanto), `templates/403.html`, `templates/404.html`, `templates/500.html`, `templates/core/inicio.html` (provisório), `tests/core/urls_erros.py`, `tests/core/test_erros.py`, `tests/seguranca/test_login_obrigatorio.py`, `tests/seguranca/test_cabecalhos.py`, `tests/seguranca/test_deploy.py`, `tests/seguranca/test_permissoes.py`
- Modify: `config/settings/base.py`, `config/settings/producao.py`, `config/urls.py`, `apps/core/views.py`, `apps/core/urls.py`

**Interfaces:**
- Produces:
  - `apps.core.erros.RegraDeNegocio(mensagem: str)`, com o atributo `.mensagem`, e `EstoqueInsuficiente(RegraDeNegocio)`.
  - `apps.core.htmx.eh_htmx(request) -> bool`.
  - `apps.core.htmx.redirecionar(request, url: str) -> HttpResponse`: se a requisição for HTMX, responde 200 com corpo vazio e o cabeçalho `HX-Redirect: url`; se não, faz um 302.
  - `apps.core.htmx.avisar(resposta, texto: str, tipo: str = "sucesso") -> HttpResponse`: acrescenta `HX-Trigger: {"aviso": {"texto": ..., "tipo": ...}}`.
  - `apps.core.middleware.LoginObrigatorioMiddleware`, subclasse de `django.contrib.auth.middleware.LoginRequiredMiddleware`.
  - Views em `apps.core.views`: `inicio` (`core:inicio`, em `/`, provisória até a Tarefa 21), `erro_403`, `erro_404`, `erro_500`, `falha_csrf` e `rota_bloqueada` (`@login_not_required`, levanta `Http404`, usada na Tarefa 5).
  - `LOGIN_URL = "/contas/login/"` (a tela de login chega na Tarefa 5).
  - As listas `ROTAS_SO_ADMIN` (vazia) e `ROTAS_LIVRES = {"core:saude"}`, mais o teste que percorre todas as rotas.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/seguranca/test_login_obrigatorio.py
ROTAS_LIVRES = {"core:saude"}  # cada tarefa que criar rota sem login acrescenta aqui, com o motivo

# todas_as_rotas() e views_por_nome() percorrem get_resolver() e consideram só as rotas com nome
# ("namespace:nome"); para montar a URL, <int:...> vira "1" e os demais conversores viram "x".
# Rota com nome que não se deixa montar assim faz o teste falhar, para ser tratada de propósito.
def test_toda_rota_exige_login(client, db):
    for nome, url in todas_as_rotas():
        if nome in ROTAS_LIVRES:
            continue
        r = client.get(url)
        assert r.status_code == 302 and r["Location"].startswith("/contas/login/"), nome

def test_so_as_rotas_livres_dispensam_login():
    livres = {nome for nome, view in views_por_nome() if not getattr(view, "login_required", True)}
    assert livres <= ROTAS_LIVRES

def test_htmx_sem_sessao_manda_o_navegador_inteiro_para_o_login(client, db):
    r = client.get("/", headers={"HX-Request": "true",
                                 "HX-Current-URL": "http://testserver/pedidos/7/editar/?aba=itens"})
    destino = urlparse(r["HX-Redirect"])
    assert r.status_code == 200 and destino.path == "/contas/login/"
    assert parse_qs(destino.query)["next"] == ["/pedidos/7/editar/?aba=itens"]

def test_htmx_com_url_de_outro_site_volta_para_o_inicio(client, db):
    r = client.get("/", headers={"HX-Request": "true", "HX-Current-URL": "https://malicioso.com/x"})
    assert parse_qs(urlparse(r["HX-Redirect"]).query)["next"] == ["/"]

# tests/seguranca/test_cabecalhos.py
def test_cabecalhos_de_seguranca(client):
    r = client.get("/saude/")
    csp = r["Content-Security-Policy"]
    for trecho in ["default-src 'self'", "script-src 'self'", "style-src 'self'",
                   "frame-ancestors 'none'", "object-src 'none'", "form-action 'self'"]:
        assert trecho in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r["X-Frame-Options"] == "DENY" and r["X-Content-Type-Options"] == "nosniff"
    assert r["Referrer-Policy"] == "same-origin" and r["Cross-Origin-Opener-Policy"] == "same-origin"

def test_sessao_expira_em_2_horas_sem_uso(settings):
    assert settings.SESSION_COOKIE_AGE == 7200 and settings.SESSION_SAVE_EVERY_REQUEST
    assert settings.SESSION_COOKIE_HTTPONLY and settings.SESSION_COOKIE_SAMESITE == "Lax"

def test_cache_fica_no_postgresql(db, settings):
    assert settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
    cache.set("teste", 1)
    assert cache.get("teste") == 1  # a tabela foi criada pela migração

# tests/seguranca/test_deploy.py
ENV_PRODUCAO_FALSA = {"DJANGO_SETTINGS_MODULE": "config.settings.producao",
                      "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
                      "DATABASE_URL": "postgres://u:p@localhost:5432/x",
                      "DJANGO_ALLOWED_HOSTS": "pedidos.exemplo.com.br"}

def test_check_deploy_sem_alertas():
    r = rodar_django("check", "--deploy", "--fail-level", "WARNING", env=ENV_PRODUCAO_FALSA)
    assert r.returncode == 0, r.stdout + r.stderr

# tests/core/test_erros.py (tests/core/urls_erros.py = rotas do config + /teste/403/ e /teste/500/)
@override_settings(ROOT_URLCONF="tests.core.urls_erros")
def test_403_no_visual_do_sistema_e_registrado(client_vendedor, caplog):
    r = client_vendedor.get("/teste/403/")
    assert r.status_code == 403 and "Voltar ao início" in r.content.decode()
    assert any("acesso negado" in m and "/teste/403/" in m for m in caplog.messages)

@override_settings(ROOT_URLCONF="tests.core.urls_erros")
def test_500_mostra_codigo_de_referencia(client_vendedor):
    client_vendedor.raise_request_exception = False
    r = client_vendedor.get("/teste/500/")
    assert r.status_code == 500 and "Código de referência:" in r.content.decode()

def test_404_no_visual_do_sistema(client_vendedor):
    r = client_vendedor.get("/nao-existe/")
    assert r.status_code == 404 and "Página não encontrada" in r.content.decode()

def test_falha_de_csrf_no_htmx_recarrega_a_pagina(vendedor):
    c = Client(enforce_csrf_checks=True)
    c.force_login(vendedor)
    r = c.post("/", headers={"HX-Request": "true"})
    assert r.status_code == 403 and r["HX-Refresh"] == "true"
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/seguranca tests/core`. Esperado: os testes de login, cabeçalhos, cache e erros falham.

- [ ] **Step 3: Implementar**
  - Ordem final do `MIDDLEWARE` (as linhas marcadas entram nas tarefas indicadas): `SecurityMiddleware`; `whitenoise.middleware.WhiteNoiseMiddleware` (Tarefa 4); `SessionMiddleware`; `CommonMiddleware`; `CsrfViewMiddleware`; `AuthenticationMiddleware`; `apps.core.middleware.LoginObrigatorioMiddleware`; `allauth.account.middleware.AccountMiddleware` (Tarefa 5); `apps.contas.middleware.PrimeiroAcessoMiddleware` (Tarefa 6); `MessageMiddleware`; `XFrameOptionsMiddleware`; `django.middleware.csp.ContentSecurityPolicyMiddleware`; `simple_history.middleware.HistoryRequestMiddleware`.
  - `LoginObrigatorioMiddleware.handle_no_permission(request, view_func)`: se não for HTMX, faz o mesmo que o Django. Se for HTMX, o `next` é o caminho e a query do `HX-Current-URL`, desde que `url_has_allowed_host_and_scheme` aceite (com `allowed_hosts={request.get_host()}`); senão, é `"/"`. Monta a query como o `redirect_to_login` do Django (`QueryDict` com `next` e `urlencode(safe="/")`, o que gera `/contas/login/?next=/pedidos/7/editar/`) e responde com `redirecionar(request, url_do_login)`.
  - CSP em `base.py`:

    ```python
    SECURE_CSP = {
        "default-src": [CSP.SELF], "script-src": [CSP.SELF], "style-src": [CSP.SELF],
        "img-src": [CSP.SELF], "font-src": [CSP.SELF], "connect-src": [CSP.SELF],
        "frame-ancestors": [CSP.NONE], "object-src": [CSP.NONE],
        "base-uri": [CSP.SELF], "form-action": [CSP.SELF],
    }
    ```

  - Também em `base.py`: `SESSION_COOKIE_AGE = 7200`, `SESSION_SAVE_EVERY_REQUEST = True`, `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `CSRF_COOKIE_SAMESITE = "Lax"`, `SECURE_REFERRER_POLICY = "same-origin"`, `SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"`, `X_FRAME_OPTIONS = "DENY"`, `CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "cache_django"}}`, `CSRF_FAILURE_VIEW = "apps.core.views.falha_csrf"` e `LOGIN_URL = "/contas/login/"`.
  - Em `producao.py`: `SECURE_SSL_REDIRECT = True`, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `SECURE_HSTS_SECONDS = 31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`, `SECURE_HSTS_PRELOAD = True`, `SESSION_COOKIE_SECURE = True` e `CSRF_COOKIE_SECURE = True`.
  - Migração `0001_tabela_cache`: `RunPython` que chama `call_command("createcachetable", database=schema_editor.connection.alias)`; o reverso não faz nada.
  - `config/urls.py`: `handler403`, `handler404` e `handler500` apontando para as views de `apps.core.views`.
  - `erro_403` registra `logging.getLogger("helptoner.seguranca").warning("acesso negado usuario=%s caminho=%s", ...)`. `erro_500` gera um código curto (`secrets.token_hex(4)`), registra-o no log junto com o erro e mostra "Código de referência: XXXXXXXX" (a Tarefa 28 passa a usar o código do Sentry). As páginas de erro estendem `base_publica.html` e têm o link "Voltar ao início".
  - `falha_csrf`: se for HTMX, responde 403 com `HX-Refresh: true`; senão, mostra `403.html` com "Sua sessão foi renovada. Recarregue a página e tente de novo."

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` passa.

- [ ] **Step 5: Commit.** `git commit -m "feat: login obrigatório, cabeçalhos de segurança e páginas de erro"`

### Tarefa 4: Identidade visual, layout e formatação

**Files:**
- Create: `scripts/css.py`, `tailwind/app.css`, `static/css/app.css` (gerado), `static/vendor/htmx.min.js`, `static/vendor/VERSOES.txt`, `static/fontes/InterVariable.woff2`, `static/fontes/OFL.txt`, `static/img/logo-helptoner.png` (cópia de `docs/assets/`), `static/js/app.js`, `templates/base.html`, `templates/componentes/{toasts,esqueleto_linhas,vazio,dialogo,paginacao,campo,selo_status}.html`, `templates/icones/*.svg`, `apps/core/dinheiro.py`, `apps/core/datas.py`, `apps/core/formatacao.py`, `apps/core/contexto.py`, `apps/core/templatetags/__init__.py`, `apps/core/templatetags/formato.py`, `tests/core/test_dinheiro.py`, `tests/core/test_formatacao.py`, `tests/core/test_layout.py`, `tests/seguranca/test_csp_nos_arquivos.py`
- Modify: `config/settings/base.py` (WhiteNoise, context processor), `templates/base_publica.html`, `templates/403.html`, `templates/404.html`, `templates/500.html`, `templates/core/inicio.html`
- Run: `uv add whitenoise`

**Interfaces:**
- Produces:
  - `apps.core.dinheiro`: `CENTAVO = Decimal("0.01")`, `arredondar(valor: Decimal) -> Decimal` (2 casas), `arredondar_custo(valor: Decimal) -> Decimal` (4 casas) e `ler_decimal_br(texto: str) -> Decimal`, que levanta `ValueError`. O ponto é sempre separador de milhar e a vírgula é a decimal, como no esboço.
  - `apps.core.datas`: `FUSO = ZoneInfo("America/Sao_Paulo")`, `hoje(agora: datetime | None = None) -> date`, `intervalo_de_datas(inicio: date, fim: date) -> tuple[datetime, datetime]` (de `inicio` às 00:00 de Brasília até o dia seguinte ao `fim` às 00:00, em UTC) e `mes_de(dia: date) -> tuple[date, date]`.
  - `apps.core.formatacao`: `brl(valor: Decimal | None) -> str`, `inteiro_br(n: int) -> str`, `numero_pedido(n: int | None) -> str`, `percentual(fracao: Decimal | None, casas: int = 1) -> str`, `data_br(valor: date | datetime | None) -> str` e `data_hora_br(valor: datetime | None) -> str`.
  - Filtros de template (`{% load formato %}`): `brl`, `inteiro`, `pedido_numero`, `pct`, `data_br` e `data_hora_br`.
  - `apps.core.contexto`: `ItemMenu(nome: str, url_name: str, icone: str, so_admin: bool)`, `itens_do_menu(usuario) -> list[ItemMenu]` e o context processor `navegacao(request) -> dict`, com as chaves `menu` (os itens já com a URL resolvida; uma rota que ainda não existe fica de fora) e `menu_ativo`.
  - Templates: `base.html` com os blocos `titulo`, `trilha` e `conteudo`; `base_publica.html` com o bloco `conteudo`; componentes `esqueleto_linhas.html` (parâmetro `linhas`), `vazio.html` (`mensagem`, `acao_url`, `acao_texto`), `dialogo.html` (`id`, `titulo`, `texto`, `acao_url`, `botao`, `perigo`, `campo_motivo`), `campo.html` (campo de formulário com rótulo e erro), `paginacao.html` ("1–20 de 38 · ‹ ›") e `selo_status.html`.
  - `app.js`: `[data-abrir-dialogo="<id>"]` abre o `<dialog>` com `showModal()`; `[data-fechar-dialogo]` fecha; `[data-alternar-menu]` abre e fecha o menu no celular; os avisos (`.toast`) somem em 3,2 s; o evento `aviso` (vindo do `HX-Trigger`) cria um aviso; `htmx:responseError` mostra "Não foi possível concluir. Tente de novo.".
  - Classes de CSS: `btn-pri`, `btn-sec`, `btn-perigo`, `cartao`, `campo`, `campo-invalido`, `rotulo`, `selo-rascunho`, `selo-confirmado`, `selo-cancelado`, `osso` (esqueleto), `toast`, `faixa`, `fx` (entrada animada), `num` (números alinhados à direita com algarismos de largura fixa) e `tabela-responsiva` (no celular, cada linha vira cartão e cada `<td data-rotulo="...">` mostra o rótulo por `::before`).
  - Padrão de lista (P18): sem HTMX, a view devolve a página com `componentes/esqueleto_linhas.html` dentro de `#resultados`, que carrega com `hx-get="{{ request.get_full_path }}" hx-trigger="load"`; com HTMX, devolve `"<template>.html#resultados"`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/core/test_dinheiro.py
@pytest.mark.parametrize("valor,esperado", [("0.005", "0.01"), ("0.015", "0.02"), ("2.675", "2.68"), ("-0.005", "-0.01")])
def test_arredondar_meio_para_cima(valor, esperado):
    assert arredondar(Decimal(valor)) == Decimal(esperado)

def test_arredondar_custo_com_4_casas():
    assert arredondar_custo(Decimal("68.888888")) == Decimal("68.8889")

@pytest.mark.parametrize("texto,esperado", [("1.234,56", "1234.56"), ("10,5", "10.5"), (" 7 ", "7"),
                                            ("1.000", "1000"), ("-3", "-3")])
def test_ler_decimal_br(texto, esperado):
    assert ler_decimal_br(texto) == Decimal(esperado)

@pytest.mark.parametrize("texto", ["", "abc", "1,2,3", "10%", "1e3", "NaN", "Infinity", "1.23,4.5"])
def test_ler_decimal_br_recusa_lixo(texto):
    with pytest.raises(ValueError):
        ler_decimal_br(texto)

# tests/core/test_formatacao.py
def test_formatos():
    assert brl(Decimal("1234.5")) == "R$ 1.234,50"
    assert brl(Decimal("1234567.891")) == "R$ 1.234.567,89"
    assert brl(Decimal("0")) == "R$ 0,00" and brl(Decimal("-254.85")) == "-R$ 254,85" and brl(None) == "—"
    assert numero_pedido(1042) == "nº 1.042" and numero_pedido(7) == "nº 7" and numero_pedido(None) == "—"
    assert inteiro_br(1234567) == "1.234.567"
    assert percentual(Decimal("0.3846")) == "38,5%" and percentual(Decimal("-0.05")) == "-5,0%"
    assert percentual(None) == "—"
    assert data_hora_br(datetime(2026, 11, 1, 1, 30, tzinfo=UTC)) == "31/10/2026 22:30"
    assert data_br(datetime(2026, 11, 1, 1, 30, tzinfo=UTC)) == "31/10/2026"
    assert data_br(date(2026, 10, 2)) == "02/10/2026"

def test_datas_de_brasilia():
    assert hoje(datetime(2026, 11, 1, 2, 0, tzinfo=UTC)) == date(2026, 10, 31)
    assert intervalo_de_datas(date(2026, 10, 1), date(2026, 10, 31)) == (
        datetime(2026, 10, 1, 3, 0, tzinfo=UTC), datetime(2026, 11, 1, 3, 0, tzinfo=UTC))
    assert mes_de(date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))

# tests/core/test_layout.py
def test_menu_por_perfil(administrador, vendedor):
    nomes = lambda u: [i.nome for i in itens_do_menu(u)]
    assert nomes(vendedor) == ["Início", "Pedidos", "Clientes", "Produtos", "Estoque"]
    assert nomes(administrador) == ["Início", "Pedidos", "Clientes", "Produtos", "Estoque",
                                    "Relatórios", "Funcionários", "Histórico"]

def test_base_usa_so_arquivos_locais_e_htmx_seguro(client_vendedor):
    html = client_vendedor.get("/").content.decode()
    assert "vendor/htmx.min.js" in html and "css/app.css" in html and "img/logo-helptoner" in html
    assert "https://" not in html
    config = html.split('name="htmx-config" content=\'')[1].split("'")[0]
    assert json.loads(config) == {"allowEval": False, "includeIndicatorStyles": False,
                                  "historyCacheSize": 0, "refreshOnHistoryMiss": True}
    assert "hx-headers=" in html and "X-CSRFToken" in html

# tests/seguranca/test_csp_nos_arquivos.py
PROIBIDO_EM_TEMPLATES = [r"\sstyle\s*=", r"<script(?![^>]*\bsrc=)", r"\son[a-z]+\s*=", r"hx-on", r"javascript:"]
PROIBIDO_NO_JS = [r"\beval\s*\(", r"new\s+Function", r"\.innerHTML\b", r"\.outerHTML\b",
                  r"insertAdjacentHTML", r"setAttribute\(\s*['\"]style"]

def test_templates_respeitam_a_csp():
    for arquivo in (BASE_DIR / "templates").rglob("*.*"):
        texto = arquivo.read_text(encoding="utf-8")
        for padrao in PROIBIDO_EM_TEMPLATES:
            assert not re.search(padrao, texto, re.I), f"{arquivo}: {padrao}"

def test_js_proprio_respeita_a_csp():  # só static/js/; static/vendor/ fica de fora
    ...  # mesmo laço, com PROIBIDO_NO_JS
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/core tests/seguranca`. Esperado: falhas de import e de template.

- [ ] **Step 3: Implementar**
  - `scripts/css.py`: fixa `VERSAO = "4.3.3"` (ou a 4.x mais recente no dia, conferida em github.com/tailwindlabs/tailwindcss/releases) e o SHA-256 dos executáveis `tailwindcss-windows-x64.exe` e `tailwindcss-linux-x64`. Baixa para `.ferramentas/` e aborta se o SHA-256 não bater. Sem argumentos, roda `-i tailwind/app.css -o static/css/app.css --minify`. Com `--observar`, acrescenta `--watch`. Com `--conferir`, gera num arquivo temporário e compara com `static/css/app.css`; se forem diferentes, sai com código 1 e a mensagem "CSS desatualizado: rode uv run python scripts/css.py".
  - `tailwind/app.css`: `@import "tailwindcss";`, `@source "../templates";` e `@source "../static/js";`. No `@theme`, as cores de §6.1: `--color-azul: #0200FF`, `--color-vermelho: #FF0000`, `--color-vermelho-texto: #D60000`, `--color-tinta: #0E1024`, `--color-fundo: #F5F6FB`, `--color-verde: #0B8A5E`, `--color-ambar: #A15C07` e `--color-serie-2: #eb6834`, mais `--font-sans: "Inter", system-ui, sans-serif`. `@font-face` com `url("../fontes/InterVariable.woff2")` (caminho relativo ao CSS gerado). Componentes em `@layer components`, copiando o visual de `docs/esbocos/identidade-visual-v3.html`: faixa com degradê `#FF0000 → #0200FF`, `.fx` com até 0,5 s, `.campo-invalido` com uma tremida leve, foco visível com `:focus-visible` em azul. Tudo desligado em `@media (prefers-reduced-motion: reduce)`.
  - HTMX 2.0.11 (o 2.0.x mais recente) em `static/vendor/htmx.min.js`; Inter 4.1 (`InterVariable.woff2` e `OFL.txt`) de github.com/rsms/inter. As versões, as origens e os SHA-256 ficam em `static/vendor/VERSOES.txt`.
  - `base.html`: `<html lang="pt-BR">`; `<meta name="htmx-config" content='{"allowEval":false,"includeIndicatorStyles":false,"historyCacheSize":0,"refreshOnHistoryMiss":true}'>`; `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`; a faixa; o menu lateral no computador e a barra no topo no celular, com o logo; os itens do `menu` com os ícones de `templates/icones/` (copiados dos SVG do esboço); o bloco do usuário (primeiro nome e perfil), o link "Minha conta" (quando a rota existir) e o botão "Sair" (formulário POST para `/contas/logout/`); as mensagens do Django viram avisos; scripts `vendor/htmx.min.js` e `js/app.js` com `defer`.
  - `WhiteNoiseMiddleware` logo depois do `SecurityMiddleware`; `apps.core.contexto.navegacao` em `context_processors`.
  - `core/inicio.html` provisório: "Olá, {{ user.primeiro_nome }}" (a Tarefa 21 completa). Páginas de erro no visual de `base_publica.html`, com o logo.
  - Rodar `uv run python scripts/css.py` para gerar `static/css/app.css`.

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` passa. A conferência visual do layout com menu fica para o fim da Tarefa 5, quando já dá para entrar no sistema local.

- [ ] **Step 5: Commit.** `git commit -m "feat: identidade visual, layout responsivo e formatação em real"`

---

## Etapa 2: Acesso

**Ao fim da etapa:** dá para entrar com e-mail, senha e código de 6 dígitos; o primeiro acesso é guiado e não pode ser pulado; existe a tela "Minha conta"; o Administrador gerencia funcionários; o painel de manutenção exige 2FA; os testes no navegador já rodam.

### Tarefa 5: Login com verificação em duas etapas, bloqueio e registro de acessos

**Files:**
- Create: `apps/contas/adapter.py`, `apps/contas/sinais.py`, `apps/contas/navegador.py`, a migração do `RegistroAcesso`, `templates/allauth/layouts/base.html` (estende `base_publica.html`), os elementos de `templates/allauth/elements/` que o allauth usa nas telas abaixo (form, fields, button, h1, p, panel), `templates/account/login.html`, `templates/mfa/authenticate.html`, `templates/429.html`, `templates/account/account_inactive.html`, `tests/contas/test_login.py`, `tests/contas/test_navegador.py`
- Modify: `config/settings/base.py`, `config/urls.py`, `apps/contas/models.py`, `apps/contas/apps.py` (o `ready()` importa `sinais`), `tests/apoio.py`, `tests/seguranca/test_login_obrigatorio.py` (acrescentar a `ROTAS_LIVRES` as rotas do allauth marcadas como livres)
- Run: `uv add "django-allauth[mfa]"`

**Interfaces:**
- Consumes: `Usuario` e `criar_usuario` (Tarefa 2).
- Produces:
  - `RegistroAcesso(email_tentado: str, usuario: Usuario | None, sucesso: bool, motivo: str, ip: str | None, navegador: str (até 300 caracteres), quando: datetime)`, ordenado por `-quando`.
  - `navegador_legivel(user_agent: str) -> str`, que devolve, por exemplo, "Chrome no Windows".
  - `ContaAdapter(DefaultAccountAdapter)`: `is_open_for_signup` devolve `False`; `authentication_failed` grava a falha com o motivo "E-mail ou senha incorretos"; `pre_authenticate` grava "Bloqueado por excesso de tentativas" quando o limite estoura (e repassa o erro); `error_messages["too_many_login_attempts"]` = "Muitas tentativas erradas. Por segurança, o acesso ficou bloqueado por alguns minutos. Tente de novo mais tarde."
  - `tests.apoio`: `ativar_2fa(usuario) -> str` (segredo), `totp_agora(segredo: str) -> str` (6 dígitos) e `codigo_totp(usuario) -> str`. A partir desta tarefa, `criar_usuario(pronto=True)` também ativa o TOTP e os códigos de recuperação.
  - Rotas do allauth usadas depois: `account_login` (`/contas/login/`), `account_logout`, `account_change_password`, `account_reauthenticate`, `mfa_authenticate`, `mfa_reauthenticate`, `mfa_activate_totp` (`/contas/2fa/totp/activate/`), `mfa_view_recovery_codes` (`/contas/2fa/recovery-codes/`), `mfa_generate_recovery_codes` e `mfa_download_recovery_codes`.
  - Textos das telas (usados pelos testes no navegador): no login, os rótulos "E-mail" e "Senha" e o botão "Entrar"; na verificação, o título "Verificação em duas etapas", o rótulo "Código de 6 dígitos", o botão "Verificar" e o texto "Perdeu o celular? Use um código de recuperação" (o mesmo campo aceita o código de recuperação).

- [ ] **Step 1: Escrever os testes que falham**

```python
UA_CHROME_WINDOWS = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

def entrar_com_senha(client, email, senha=SENHA_TESTE, **kw):
    return client.post("/contas/login/", {"login": email, "password": senha}, **kw)

def test_login_com_senha_e_codigo(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    r = entrar_com_senha(client, "CARLA@helptoner.com.br")
    assert r.status_code == 302 and r["Location"] == "/contas/2fa/authenticate/"
    r = client.post("/contas/2fa/authenticate/", {"code": codigo_totp(u)})
    assert r.status_code == 302 and r["Location"] == "/"
    assert client.get("/").status_code == 200
    assert RegistroAcesso.objects.filter(usuario=u, sucesso=True).count() == 1

def test_codigo_errado_nao_entra_e_fica_registrado(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    entrar_com_senha(client, u.email)
    client.post("/contas/2fa/authenticate/", {"code": "000000"})
    assert client.get("/").status_code == 302
    assert RegistroAcesso.objects.get(sucesso=False).motivo == "Código de verificação inválido"

def test_senha_errada_fica_registrada_com_ip_e_navegador(client, db):
    criar_usuario(email="carla@helptoner.com.br")
    entrar_com_senha(client, "carla@helptoner.com.br", "senha-errada-de-novo", headers={"User-Agent": UA_CHROME_WINDOWS})
    reg = RegistroAcesso.objects.get()
    assert (reg.sucesso, reg.email_tentado, reg.motivo, reg.ip, reg.navegador) == (
        False, "carla@helptoner.com.br", "E-mail ou senha incorretos", "127.0.0.1", UA_CHROME_WINDOWS)

def test_bloqueio_da_conta_depois_de_5_erros_usa_o_cache_do_banco(client, db):
    criar_usuario(email="carla@helptoner.com.br")
    for _ in range(5):
        entrar_com_senha(client, "carla@helptoner.com.br", "senha-errada-de-novo")
    r = entrar_com_senha(client, "carla@helptoner.com.br")  # senha certa, mas bloqueada
    assert "Muitas tentativas erradas" in r.content.decode() and r.status_code == 200
    with connection.cursor() as c:
        c.execute("select count(*) from cache_django")
        assert c.fetchone()[0] > 0

def test_bloqueio_por_ip_depois_de_10_erros(client, db):
    for i in range(10):
        entrar_com_senha(client, f"ninguem{i}@x.com", "senha-errada-de-novo")
    r = entrar_com_senha(client, "outro@x.com", "senha-errada-de-novo")
    assert "Muitas tentativas erradas" in r.content.decode()

@override_settings(ALLAUTH_TRUSTED_CLIENT_IP_HEADER="x-vercel-forwarded-for")
def test_ip_vem_so_do_cabecalho_confiavel(client, db):
    entrar_com_senha(client, "x@x.com", "senha-errada-de-novo",
                     headers={"x-vercel-forwarded-for": "200.1.2.3", "x-forwarded-for": "6.6.6.6"})
    assert RegistroAcesso.objects.get().ip == "200.1.2.3"

@pytest.mark.parametrize("url", ["/contas/signup/", "/contas/password/reset/", "/contas/email/",
                                 "/contas/2fa/totp/deactivate/"])
def test_rotas_do_allauth_desligadas(client, db, url):
    assert client.get(url).status_code == 404

def test_usuario_desativado_nao_entra(client, db):
    u = criar_usuario(email="carla@helptoner.com.br")
    Usuario.objects.filter(pk=u.pk).update(is_active=False)
    entrar_com_senha(client, u.email)
    assert client.get("/").status_code == 302
    assert not RegistroAcesso.objects.filter(sucesso=True).exists()

# tests/contas/test_navegador.py
@pytest.mark.parametrize("ua,esperado", [
    (UA_CHROME_WINDOWS, "Chrome no Windows"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36 Edg/141.0", "Edge no Windows"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1", "Safari no iPhone"),
    ("Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36", "Chrome no Android"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:131.0) Gecko/20100101 Firefox/131.0", "Firefox no Mac"),
    ("", "Navegador desconhecido"),
])
def test_navegador_legivel(ua, esperado):
    assert navegador_legivel(ua) == esperado
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/contas`. Esperado: 404 em `/contas/login/`.

- [ ] **Step 3: Implementar**
  - Acrescentar `allauth`, `allauth.account` e `allauth.mfa` a `INSTALLED_APPS` e o `AccountMiddleware` na posição combinada na Tarefa 3. Configuração em `base.py`:

    ```python
    AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]
    ACCOUNT_ADAPTER = "apps.contas.adapter.ContaAdapter"
    ACCOUNT_LOGIN_METHODS = {"email"}
    ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
    ACCOUNT_USER_MODEL_USERNAME_FIELD = None
    ACCOUNT_EMAIL_VERIFICATION = "none"
    ACCOUNT_UNIQUE_EMAIL = True
    ACCOUNT_SESSION_REMEMBER = False
    ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = False
    ACCOUNT_RATE_LIMITS = {"login": "30/m/ip", "login_failed": "10/m/ip,5/5m/key"}
    MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
    MFA_TOTP_ISSUER = "Helptoner Pedidos"
    MFA_RECOVERY_CODE_COUNT = 10
    ALLAUTH_TRUSTED_CLIENT_IP_HEADER = None  # em produção: "x-vercel-forwarded-for" (Tarefa 28)
    LOGIN_REDIRECT_URL = "/"
    ```

  - `config/urls.py`: antes do `path("contas/", include("allauth.urls"))`, colocar `re_path(r"^contas/(signup|email|confirm-email|password/(set|reset)|login/code|2fa/totp/deactivate)(/.*)?$", rota_bloqueada)`.
  - `sinais.py`: o receptor de `django.contrib.auth.signals.user_logged_in` grava o sucesso; o receptor de `allauth.mfa.signals.authentication_failed` (só quando `reauthentication=False`) grava "Código de verificação inválido". O IP vem de `allauth.account.adapter.get_adapter(request).get_client_ip(request)`; se essa chamada levantar `PermissionDenied` (requisição sem IP, como no `force_login` dos testes), grava `None`. O navegador é o `HTTP_USER_AGENT` cortado em 300 caracteres.
  - `navegador_legivel`: identifica o navegador (Edge pelo `Edg/` antes de Chrome; Chrome; Firefox; Safari) e o sistema (Windows, Android, iPhone, iPad, Mac, Linux), com respostas no formato "<navegador> no <sistema>".
  - Templates com o visual de `docs/esbocos/telas.html` (Acesso): logo, cartão central e a verificação com 6 dígitos.
  - `tests.apoio.totp_agora(segredo)`: `f"{hotp_value(segredo, int(time.time()) // 30):06d}"`, usando `allauth.mfa.totp.internal.auth.hotp_value`. `ativar_2fa` usa `generate_totp_secret` e `TOTP.activate` (de `allauth.mfa.totp.internal.auth`) e `RecoveryCodes.activate` (de `allauth.mfa.recovery_codes.internal.auth`). `codigo_totp` lê o segredo do `Authenticator` do tipo TOTP com `allauth.mfa.adapter.get_adapter().decrypt(...)`. Essas APIs internas do allauth só podem aparecer nos testes. O allauth recusa o mesmo código duas vezes na mesma janela de 30 s, então cada teste usa cada código uma vez só.

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` passa (o teste de rotas livres mostra quais rotas do allauth entram em `ROTAS_LIVRES`). Depois, criar um usuário local com `uv run python manage.py createsuperuser`, entrar em http://localhost:8000/ (sem 2FA configurado, ele entra só com a senha; o primeiro acesso guiado chega na Tarefa 6) e comparar o login e o layout com `docs/esbocos/telas.html` e `identidade-visual-v3.html`, no computador e na largura de celular (DevTools).

- [ ] **Step 5: Commit.** `git commit -m "feat: login com verificação em duas etapas, bloqueio e registro de acessos"`

### Tarefa 6: Primeiro acesso e Minha conta

**Files:**
- Create: `apps/contas/middleware.py`, `apps/contas/forms.py`, `apps/contas/views.py`, `apps/contas/urls.py`, `templates/contas/primeiro_acesso_senha.html`, `templates/contas/minha_conta.html`, `templates/mfa/totp/activate_form.html`, `templates/mfa/recovery_codes/index.html`, `templates/mfa/recovery_codes/generate.html`, `templates/mfa/index.html`, `templates/mfa/reauthenticate.html`, `templates/account/reauthenticate.html`, `templates/account/password_change.html`, `tests/contas/test_primeiro_acesso.py`, `tests/contas/test_minha_conta.py`
- Modify: `config/settings/base.py` (middleware), `config/urls.py`, `apps/contas/sinais.py`

**Interfaces:**
- Consumes: as rotas do allauth (Tarefa 5) e os campos `deve_trocar_senha` e `codigos_recuperacao_entregues` (Tarefa 2).
- Produces:
  - Rotas `contas:primeiro_acesso_senha` (`/primeiro-acesso/senha/`), `contas:primeiro_acesso_concluir` (`/primeiro-acesso/concluir/`, só POST) e `contas:minha_conta` (`/minha-conta/`).
  - `PrimeiroAcessoMiddleware`, que, para usuário logado, define a etapa e as rotas permitidas nela:
    - **Etapa 1:** `deve_trocar_senha` → só `contas:primeiro_acesso_senha`.
    - **Etapa 2:** códigos não entregues e sem TOTP → só `mfa_activate_totp`.
    - **Etapa 3:** códigos não entregues e com TOTP → só `mfa_view_recovery_codes`, `mfa_download_recovery_codes` e `contas:primeiro_acesso_concluir`.
    - Em qualquer etapa, também `account_logout`, `account_reauthenticate`, `mfa_reauthenticate` e `core:saude`. Qualquer outra rota é redirecionada para a etapa atual (com `redirecionar`, que cobre o HTMX). O banco só é consultado quando os códigos ainda não foram entregues.
  - Receptor extra de `user_logged_in`: se o usuário não tem TOTP, marca `codigos_recuperacao_entregues=False`, o que força a etapa 2 (protege contra um TOTP apagado por fora).
  - Textos da etapa 1 (usados pelos testes no navegador): os rótulos "Nova senha" e "Confirme a nova senha" e o botão "Salvar e continuar".
  - Atenção: o allauth exige autenticação recente (registrada pelo login de verdade) para ativar o TOTP e gerar códigos. Por isso, o teste do fluxo completo entra pelo formulário de login, e não com `force_login`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_primeiro_acesso_obrigatorio_e_completo(client, db):
    u = criar_usuario(pronto=False, email="nova@helptoner.com.br")  # deve trocar a senha e não tem 2FA
    r = client.post("/contas/login/", {"login": u.email, "password": SENHA_TESTE})  # sem 2FA: entra só com a senha
    assert r.status_code == 302
    for url in ["/", "/minha-conta/"]:
        assert client.get(url)["Location"] == "/primeiro-acesso/senha/"
    assert client.get("/", headers={"HX-Request": "true"})["HX-Redirect"] == "/primeiro-acesso/senha/"
    r = client.post("/primeiro-acesso/senha/", {"new_password1": SENHA_TESTE, "new_password2": SENHA_TESTE})
    assert "A nova senha precisa ser diferente da senha temporária." in r.content.decode()
    nova = "toner-azul-de-março"
    client.post("/primeiro-acesso/senha/", {"new_password1": nova, "new_password2": nova})
    assert client.get("/")["Location"] == "/contas/2fa/totp/activate/"
    r = client.get("/contas/2fa/totp/activate/")
    segredo = r.context["form"].secret
    assert "<svg" in r.content.decode() and segredo in r.content.decode().replace(" ", "")
    r = client.post("/contas/2fa/totp/activate/", {"code": totp_agora(segredo)})
    assert r["Location"] == "/contas/2fa/recovery-codes/"
    assert client.get("/")["Location"] == "/contas/2fa/recovery-codes/"
    r = client.get("/contas/2fa/recovery-codes/")
    assert "Guardei os códigos, continuar" in r.content.decode()
    assert client.post("/primeiro-acesso/concluir/")["Location"] == "/"
    assert client.get("/").status_code == 200

def test_sair_e_permitido_no_primeiro_acesso(client, db):
    client.force_login(criar_usuario(pronto=False))
    assert client.post("/contas/logout/").status_code == 302
    assert client.get("/")["Location"].startswith("/contas/login/")

def test_totp_apagado_por_fora_volta_para_a_etapa_2(client, db):
    u = criar_usuario()
    Authenticator.objects.filter(user=u).delete()
    client.force_login(u)  # dispara user_logged_in
    assert client.get("/")["Location"] == "/contas/2fa/totp/activate/"

def test_concluir_sem_totp_nao_conclui(client, db):
    u = criar_usuario(pronto=False)
    Usuario.objects.filter(pk=u.pk).update(deve_trocar_senha=False)
    client.force_login(u)
    client.post("/primeiro-acesso/concluir/")
    u.refresh_from_db()
    assert not u.codigos_recuperacao_entregues

# tests/contas/test_minha_conta.py
def test_minha_conta_mostra_dados_e_atalhos(client_vendedor):
    html = client_vendedor.get("/minha-conta/").content.decode()
    assert "carla@helptoner.com.br" in html and "Vendedor" in html
    assert "/contas/password/change/" in html and "/contas/2fa/recovery-codes/generate/" in html

def test_trocar_senha_exige_a_atual(client_vendedor):
    r = client_vendedor.post("/contas/password/change/", {"oldpassword": "errada-errada-1",
                             "password1": "toner-azul-de-março", "password2": "toner-azul-de-março"})
    assert r.status_code == 200  # formulário com erro; senha mantida
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/contas`. Esperado: o usuário novo entra direto em `/`.

- [ ] **Step 3: Implementar**
  - `primeiro_acesso_senha`: usa o `SetPasswordForm` do Django e recusa senha igual à atual. Se der certo, grava `deve_trocar_senha=False`, chama `update_session_auth_hash` e redireciona para `/` (o middleware leva à próxima etapa).
  - `primeiro_acesso_concluir` (POST): só conclui se o usuário tiver TOTP. Grava `codigos_recuperacao_entregues=True`, mostra o aviso "Tudo pronto! Seu acesso está configurado." e redireciona para `/`.
  - `mfa/totp/activate_form.html`: título "Primeiro acesso" com os passos (1 · Nova senha ✓, 2 · Autenticador, 3 · Códigos de recuperação), como em `telas.html`; QR code com `{{ totp_svg|safe }}` (SVG inline, sem `data:`; a CSP não libera `data:`); o segredo em texto, em grupos de 4, num elemento `data-segredo`, com a frase "Não consegue ler o QR? Digite esta chave no aplicativo"; o campo "Código de 6 dígitos"; o botão "Ativar e continuar".
  - `mfa/recovery_codes/index.html`: lista os códigos (`unused_codes`), tem o link "Baixar" e, quando `not user.codigos_recuperacao_entregues`, o formulário POST para `contas:primeiro_acesso_concluir` com o botão "Guardei os códigos, continuar".
  - `minha_conta`: nome, e-mail e perfil, mais os links "Trocar senha" e "Gerar novos códigos de recuperação". O link "Minha conta" do menu aponta para cá.
  - `mfa/index.html`: só leva de volta para "Minha conta" (a tela padrão do allauth não é usada).

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` passa.

- [ ] **Step 5: Commit.** `git commit -m "feat: primeiro acesso guiado e Minha conta"`

### Tarefa 7: Testes no navegador (Playwright) e fluxo de login

**Files:**
- Create: `tests/e2e/__init__.py`, `tests/e2e/conftest.py`, `tests/e2e/test_acesso.py`
- Run: `uv add --dev pytest-playwright` e `uv run playwright install chromium`

**Interfaces:**
- Consumes: `criar_usuario`, `codigo_totp` e `totp_agora` (Tarefa 5) e os textos das telas de login (Tarefa 5).
- Produces (em `tests/e2e/conftest.py`):
  - Fixture `pagina(page, live_server) -> Page`, que guarda as mensagens do console e os erros da página e, no fim do teste, falha se alguma mensagem tiver "Content Security Policy" ou "Refused to".
  - `entrar(pagina, live_server, usuario) -> None`, que faz o login com senha e código e espera ver "Olá, {primeiro_nome}".
  - Todo módulo de e2e declara `pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]`. O `conftest` faz `os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_login_com_2fa(pagina, live_server, administrador):
    entrar(pagina, live_server, administrador)
    pagina.get_by_role("button", name="Sair").click()
    expect(pagina.get_by_label("E-mail")).to_be_visible()

def test_primeiro_acesso_completo(pagina, live_server, db):
    u = criar_usuario(pronto=False, email="nova@helptoner.com.br", nome="Nova Pessoa")
    pagina.goto(live_server.url + "/")
    pagina.get_by_label("E-mail").fill(u.email)
    pagina.get_by_label("Senha").fill(SENHA_TESTE)
    pagina.get_by_role("button", name="Entrar").click()
    pagina.get_by_label("Nova senha", exact=True).fill("toner-azul-de-março")
    pagina.get_by_label("Confirme a nova senha").fill("toner-azul-de-março")
    pagina.get_by_role("button", name="Salvar e continuar").click()
    segredo = pagina.locator("[data-segredo]").inner_text().replace(" ", "")
    pagina.get_by_label("Código de 6 dígitos").fill(totp_agora(segredo))
    pagina.get_by_role("button", name="Ativar e continuar").click()
    pagina.get_by_role("button", name="Guardei os códigos, continuar").click()
    expect(pagina.get_by_text("Olá, Nova")).to_be_visible()
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest -m e2e`. Esperado: erro de fixture (`pagina` e `entrar` ainda não existem).

- [ ] **Step 3: Implementar** o `conftest` descrito em Interfaces e ajustar os templates, se faltar algum rótulo acessível.

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest -m e2e` passa, sem violação de CSP (isso também confere o QR code em SVG inline).

- [ ] **Step 5: Commit.** `git commit -m "test: testes no navegador para login e primeiro acesso"`

### Tarefa 8: Funcionários, primeiro administrador e painel de manutenção

**Files:**
- Create: `apps/contas/services.py`, `apps/contas/management/__init__.py`, `apps/contas/management/commands/__init__.py`, `apps/contas/management/commands/criar_primeiro_admin.py`, `templates/contas/funcionarios.html`, `templates/contas/funcionario_form.html`, `templates/contas/senha_temporaria.html`, `tests/contas/test_funcionarios_services.py`, `tests/contas/test_funcionarios_telas.py`, `tests/contas/test_comando.py`, `tests/contas/test_painel.py`
- Modify: `apps/contas/views.py`, `apps/contas/urls.py`, `apps/contas/forms.py`, `apps/contas/admin.py`, `config/urls.py`, `config/settings/base.py` (`ADMIN_URL`), `tests/seguranca/test_permissoes.py`, `tests/seguranca/test_login_obrigatorio.py`

**Interfaces:**
- Consumes: `exigir_administrador` e `requer_administrador` (Tarefa 2) e `RegraDeNegocio` (Tarefa 3).
- Produces (em `apps/contas/services.py`; cada função começa com `exigir_administrador(por)` e grava `usuario._history_user = por` e `usuario._change_reason` antes do `save()`):
  - `gerar_senha_temporaria() -> str`: 16 caracteres sorteados com `secrets` do alfabeto `ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789`, em 4 grupos separados por "-".
  - `criar_funcionario(*, nome: str, email: str, perfil: str, por) -> tuple[Usuario, str]`, com o motivo "Funcionário criado".
  - `alterar_funcionario(usuario, *, nome: str, perfil: str, por) -> Usuario`, com o motivo "Perfil: Vendedor → Administrador" quando o perfil muda.
  - `redefinir_senha(usuario, *, por) -> str`, com o motivo "Senha redefinida".
  - `zerar_2fa(usuario, *, por) -> None`, com o motivo "Verificação em duas etapas zerada".
  - `desativar_funcionario(usuario, *, por) -> None`, com o motivo "Funcionário desativado".
  - Rotas: `contas:funcionarios` (`/funcionarios/`), `contas:funcionario_novo` (`/funcionarios/novo/`), `contas:funcionario_editar` (`/funcionarios/<id>/`), `contas:funcionario_redefinir_senha`, `contas:funcionario_zerar_2fa` e `contas:funcionario_desativar` (`/funcionarios/<id>/redefinir-senha/`, `/zerar-2fa/` e `/desativar/`, só POST).
  - Comando `criar_primeiro_admin --email E --nome N`.
  - `settings.ADMIN_URL = os.environ.get("ADMIN_URL", "manutencao/")`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_criar_funcionario_gera_senha_temporaria(administrador):
    u, senha = criar_funcionario(nome="Ana Lima", email="Ana@Helptoner.com.br", perfil=VENDEDOR, por=administrador)
    assert u.email == "ana@helptoner.com.br" and u.perfil == "Vendedor" and u.deve_trocar_senha
    assert len(senha.replace("-", "")) == 16 and u.check_password(senha)
    assert u.history.first().history_change_reason == "Funcionário criado"
    assert u.history.first().history_user == administrador

def test_so_administrador_gerencia_funcionarios(vendedor):
    with pytest.raises(PermissionDenied):
        criar_funcionario(nome="X", email="x@x.com", perfil=VENDEDOR, por=vendedor)

def test_email_repetido(administrador, vendedor):
    with pytest.raises(RegraDeNegocio, match="Já existe um funcionário com este e-mail."):
        criar_funcionario(nome="X", email="CARLA@helptoner.com.br", perfil=VENDEDOR, por=administrador)

def test_redefinir_senha_derruba_a_sessao(client, administrador, vendedor):
    client.force_login(vendedor)
    redefinir_senha(vendedor, por=administrador)
    assert client.get("/")["Location"].startswith("/contas/login/")
    vendedor.refresh_from_db()
    assert vendedor.deve_trocar_senha

def test_zerar_2fa_leva_de_volta_a_configuracao(client, administrador, vendedor):
    client.force_login(vendedor)
    zerar_2fa(vendedor, por=administrador)
    assert not Authenticator.objects.filter(user=vendedor).exists()
    assert client.get("/")["Location"] == "/contas/2fa/totp/activate/"

def test_desativar_tira_o_acesso_na_hora(client, administrador, vendedor):
    client.force_login(vendedor)
    desativar_funcionario(vendedor, por=administrador)
    assert client.get("/")["Location"].startswith("/contas/login/")

def test_administrador_nao_mexe_em_si_mesmo(administrador):
    with pytest.raises(RegraDeNegocio, match="Você não pode desativar a si mesmo."):
        desativar_funcionario(administrador, por=administrador)
    with pytest.raises(RegraDeNegocio, match="Você não pode mudar o seu próprio perfil."):
        alterar_funcionario(administrador, nome="Lucas", perfil=VENDEDOR, por=administrador)

# tests/contas/test_funcionarios_telas.py
def test_novo_funcionario_mostra_a_senha_uma_vez_so(client_admin):
    r = client_admin.post("/funcionarios/novo/", {"nome": "Ana Lima", "email": "ana@helptoner.com.br", "perfil": "Vendedor"})
    assert "Copie e repasse ao funcionário" in r.content.decode() and "no-store" in r["Cache-Control"]
    lista = client_admin.get("/funcionarios/", headers={"HX-Request": "true"}).content.decode()
    assert "Ana Lima" in lista and "Pendente" in lista

# tests/contas/test_comando.py
def test_criar_primeiro_admin(db):
    saida = StringIO()
    call_command("criar_primeiro_admin", email="lucas@helptoner.com.br", nome="Lucas Tonnon", stdout=saida)
    u = Usuario.objects.get()
    assert u.is_superuser and u.is_staff and u.eh_administrador and u.deve_trocar_senha
    senha = re.search(r"Senha temporária: (\S+)", saida.getvalue()).group(1)
    assert u.check_password(senha)
    with pytest.raises(CommandError, match="Já existe"):
        call_command("criar_primeiro_admin", email="lucas@helptoner.com.br", nome="Lucas", stdout=StringIO())

# tests/contas/test_painel.py
def test_painel_pede_login_do_sistema(client, db):
    assert client.get("/manutencao/")["Location"] == "/contas/login/?next=/manutencao/"

def test_administrador_comum_nao_entra_no_painel(client_admin):
    assert client_admin.get("/manutencao/", follow=True).status_code == 403

def test_superusuario_entra_no_painel(client, db):
    su = criar_usuario(ADMINISTRADOR, email="su@helptoner.com.br")
    Usuario.objects.filter(pk=su.pk).update(is_staff=True, is_superuser=True)
    client.force_login(su)
    assert client.get("/manutencao/").status_code == 200

# tests/seguranca/test_permissoes.py
ROTAS_SO_ADMIN += [("get", "/funcionarios/"), ("get", "/funcionarios/novo/"), ("get", "/funcionarios/1/"),
                   ("post", "/funcionarios/1/redefinir-senha/"), ("post", "/funcionarios/1/zerar-2fa/"),
                   ("post", "/funcionarios/1/desativar/")]

@pytest.mark.parametrize("metodo,url", ROTAS_SO_ADMIN)
def test_vendedor_recebe_403(client_vendedor, metodo, url):
    assert getattr(client_vendedor, metodo)(url).status_code == 403
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/contas tests/seguranca`.

- [ ] **Step 3: Implementar**
  - Views com `@requer_administrador` como decorator **mais externo**, para devolver 403 antes de procurar o objeto. Lista no padrão P18, com as colunas de `telas.html`: Nome, E-mail, Perfil, 2FA ("Ativo" ou "Pendente", conforme `codigos_recuperacao_entregues`) e Situação.
  - Na criação e na redefinição, a resposta do POST mostra `senha_temporaria.html` com `Cache-Control: no-store` e o texto "Copie e repasse ao funcionário. Ela não será mostrada de novo." A senha não fica gravada em lugar nenhum.
  - Desativar e zerar o 2FA usam `componentes/dialogo.html` para pedir confirmação.
  - Painel: em `config/urls.py`, `path(settings.ADMIN_URL, admin.site.urls)`, `admin.site.login = secure_admin_login(admin.site.login)` (de `allauth.account.decorators`) e `admin.site.has_permission = lambda r: r.user.is_active and r.user.is_superuser`. Registrar `RegistroAcesso` no admin só para leitura.
  - O comando cria o superusuário no grupo Administrador com senha temporária, `deve_trocar_senha=True`, e imprime "Senha temporária: XXXX".

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` e `uv run pytest -m e2e` passam.

- [ ] **Step 5: Commit.** `git commit -m "feat: gestão de funcionários, primeiro administrador e painel protegido"`

---

## Etapa 3: Cadastros

**Ao fim da etapa:** clientes (pessoa ou empresa) e produtos podem ser cadastrados, buscados, editados, inativados e reativados, e as alterações ficam no histórico.

### Tarefa 9: CPF e CNPJ (incluindo o CNPJ alfanumérico)

**Files:**
- Create: `apps/cadastros/__init__.py`, `apps/cadastros/apps.py`, `apps/cadastros/documentos.py`, `apps/cadastros/templatetags/__init__.py`, `apps/cadastros/templatetags/cadastros.py`, `tests/cadastros/test_documentos.py`
- Modify: `config/settings/base.py` (`apps.cadastros`)

**Interfaces:**
- Produces (em `apps.cadastros.documentos`; os tipos são as strings `"PF"` e `"PJ"`):
  - `normalizar_documento(texto: str) -> str`: tira tudo que não for letra ou dígito e passa para maiúsculas.
  - `digitos_verificadores_cpf(base9: str) -> str` e `digitos_verificadores_cnpj(base12: str) -> str`.
  - `cpf_valido(doc: str) -> bool`: 11 dígitos, nem todos iguais, com os verificadores certos.
  - `cnpj_valido(doc: str) -> bool`: 12 caracteres `[0-9A-Z]` mais 2 dígitos, nem todos iguais. Cada caractere vale `ord(c) - 48`; os pesos vão de 2 a 9, da direita para a esquerda, recomeçando depois do 9; se o resto da divisão por 11 for menor que 2, o dígito é 0, senão é 11 menos o resto.
  - `validar_documento(tipo: str, texto: str) -> str`: normaliza e devolve o documento, ou levanta `ValidationError` com "CPF inválido: confira os dígitos." ou "CNPJ inválido: confira os dígitos.".
  - `formatar_documento(tipo: str, doc: str) -> str`.
  - Filtro de template `{{ cliente.documento|documento:cliente.tipo }}`.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.mark.parametrize("doc", ["12345678909", "52998224725"])
def test_cpf_valido(doc):
    assert cpf_valido(doc)

@pytest.mark.parametrize("doc", ["12345678900", "11111111111", "1234567890", "1234567890A", ""])
def test_cpf_invalido(doc):
    assert not cpf_valido(doc)

@pytest.mark.parametrize("doc", ["11222333000181", "12ABC34501DE35"])
def test_cnpj_valido(doc):
    assert cnpj_valido(doc)

@pytest.mark.parametrize("doc", ["12345678000199", "00000000000000", "12ABC34501DE36", "12abc34501de35",
                                 "12ABC34501DEAB", "1122233300018"])
def test_cnpj_invalido(doc):
    assert not cnpj_valido(doc)

def test_digitos_verificadores():
    assert digitos_verificadores_cnpj("12ABC34501DE") == "35"
    assert digitos_verificadores_cpf("123456789") == "09"

def test_validar_documento_aceita_mascara_e_minusculas():
    assert validar_documento("PJ", "12.abc.345/01de-35") == "12ABC34501DE35"
    assert validar_documento("PF", "123.456.789-09") == "12345678909"
    with pytest.raises(ValidationError, match="CNPJ inválido: confira os dígitos."):
        validar_documento("PJ", "12.345.678/0001-99")
    with pytest.raises(ValidationError, match="CPF inválido: confira os dígitos."):
        validar_documento("PF", "11.222.333/0001-81")

def test_formatar_documento():
    assert formatar_documento("PF", "12345678909") == "123.456.789-09"
    assert formatar_documento("PJ", "12ABC34501DE35") == "12.ABC.345/01DE-35"
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/cadastros/test_documentos.py`.
- [ ] **Step 3: Implementar** as funções da seção Interfaces.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest tests/cadastros`.
- [ ] **Step 5: Commit.** `git commit -m "feat: validação de CPF e CNPJ, incluindo o CNPJ alfanumérico"`

### Tarefa 10: Clientes

**Files:**
- Create: `apps/cadastros/models.py`, `apps/cadastros/forms.py`, `apps/cadastros/views.py`, `apps/cadastros/urls.py`, `apps/cadastros/buscas.py`, `apps/cadastros/admin.py`, `apps/cadastros/migrations/0001_initial.py` (com `UnaccentExtension()` antes do `CreateModel`), `templates/cadastros/clientes.html` (com o partial `resultados`), `templates/cadastros/cliente_form.html`, `static/js/mascaras.js`, `tests/cadastros/test_clientes.py`, `tests/cadastros/test_busca_clientes.py`
- Modify: `config/settings/base.py` (`django.contrib.postgres`), `config/urls.py`, `tests/apoio.py`

**Interfaces:**
- Consumes: `validar_documento` e `normalizar_documento` (Tarefa 9).
- Produces:
  - `Cliente`: `tipo` (`TipoPessoa.PF` "Pessoa" ou `TipoPessoa.PJ` "Empresa"), `nome` (200), `documento` (14, único), `telefone`, `email`, `cep` (8 dígitos), `logradouro`, `numero`, `complemento`, `bairro`, `cidade`, `uf` (as 27 UFs), `observacoes`, `ativo`, `criado_em`, `atualizado_em`; propriedade `codigo` (devolve o `pk`); `history = HistoricalRecords(excluded_fields=["atualizado_em"])`; ordenado por `nome`.
  - Em `apps.cadastros.buscas`: `normalizar_busca(texto: str) -> str` (tira espaços das pontas, junta espaços repetidos e corta em 100 caracteres) e `buscar_clientes(texto: str, *, incluir_inativos: bool = False, limite: int | None = None) -> QuerySet[Cliente]`. A busca usa `nome__unaccent__icontains` e, quando o documento normalizado do texto tem 3 caracteres ou mais, também `documento__contains`.
  - Rotas: `cadastros:clientes` (`/clientes/`), `cadastros:cliente_novo` (`/clientes/novo/`), `cadastros:cliente_editar` (`/clientes/<id>/`), `cadastros:cliente_inativar` e `cadastros:cliente_reativar` (`/clientes/<id>/inativar/` e `/reativar/`, só POST). Todas abertas ao Vendedor.
  - `tests.apoio.criar_cliente(nome="Papelaria Central Ltda", *, tipo="PJ", documento=None, **campos) -> Cliente`. Sem `documento`, gera um válido e único com `digitos_verificadores_*`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_cadastrar_empresa(client_vendedor):
    client_vendedor.post("/clientes/novo/", {"tipo": "PJ", "nome": "Papelaria Central Ltda",
                         "documento": "11.222.333/0001-81", "cep": "13010-000", "uf": "SP", "cidade": "Campinas"})
    c = Cliente.objects.get()
    assert (c.documento, c.cep, c.ativo, c.codigo) == ("11222333000181", "13010000", True, c.pk)

def test_documento_invalido_mostra_erro_e_nao_grava(client_vendedor):
    r = client_vendedor.post("/clientes/novo/", {"tipo": "PJ", "nome": "X", "documento": "12.345.678/0001-99"})
    assert "CNPJ inválido: confira os dígitos." in r.content.decode() and not Cliente.objects.exists()

def test_documento_repetido_mostra_quem_ja_tem(client_vendedor):
    criar_cliente("Papelaria Central Ltda", documento="11222333000181")
    r = client_vendedor.post("/clientes/novo/", {"tipo": "PJ", "nome": "Outra", "documento": "11.222.333/0001-81"})
    assert "Já existe um cliente com este CPF/CNPJ: Papelaria Central Ltda." in r.content.decode()

def test_obrigatorios(client_vendedor):
    r = client_vendedor.post("/clientes/novo/", {"tipo": "PF"})
    assert r.content.decode().count("Este campo é obrigatório.") == 2  # documento e nome

def test_inativar_e_reativar(client_vendedor):
    c = criar_cliente()
    client_vendedor.post(f"/clientes/{c.pk}/inativar/")
    c.refresh_from_db()
    assert not c.ativo
    client_vendedor.post(f"/clientes/{c.pk}/reativar/")
    c.refresh_from_db()
    assert c.ativo

def test_alteracao_vai_para_o_historico(client_vendedor, vendedor):
    c = criar_cliente()
    dados = {"tipo": c.tipo, "nome": c.nome, "documento": c.documento, "telefone": "(19) 99999-0000"}
    client_vendedor.post(f"/clientes/{c.pk}/", dados)
    assert c.history.count() == 2 and c.history.first().history_user == vendedor

def test_lista_htmx_e_lista_vazia(client_vendedor):
    assert "Nenhum cliente ainda. Cadastre o primeiro." in client_vendedor.get(
        "/clientes/", headers={"HX-Request": "true"}).content.decode()
    criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    r = client_vendedor.get("/clientes/?q=joao", headers={"HX-Request": "true"})
    assert "João da Silva" in r.content.decode() and "<html" not in r.content.decode()

# tests/cadastros/test_busca_clientes.py
@pytest.mark.parametrize("texto", ["joao", "JOÃO", "joão da", "123.456", "12345678909", "678909"])
def test_busca_acha_do_jeito_que_se_digita(db, texto):
    joao = criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    criar_cliente("Maria Souza", tipo="PF")
    assert list(buscar_clientes(texto)) == [joao]

@pytest.mark.parametrize("texto", ["%", "_", "'", "\\", "joao%"])
def test_caracteres_especiais_nao_quebram(db, texto):
    criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    assert list(buscar_clientes(texto)) == []

def test_inativo_fica_fora_da_busca(db):
    c = criar_cliente("João da Silva", tipo="PF", documento="12345678909", ativo=False)
    assert list(buscar_clientes("joao")) == [] and list(buscar_clientes("joao", incluir_inativos=True)) == [c]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/cadastros`.
- [ ] **Step 3: Implementar**
  - `Cliente.clean()`: valida o documento conforme o tipo, o CEP (8 dígitos depois de normalizar) e a UF. A unicidade é conferida no formulário, com a mensagem do teste.
  - Lista (padrão P18): busca enquanto se digita (`hx-get` com `hx-trigger="input changed delay:300ms"`), a opção "Mostrar inativos", as colunas Nome, CPF/CNPJ, Cidade/UF, Telefone e Situação, com `tabela-responsiva`.
  - Formulário (sem o campo `ativo`, que só muda por inativar e reativar): Pessoa ou Empresa num seletor segmentado (rádios); documento, CEP e telefone com máscara (`mascaras.js`, ligado por `data-mascara="cpf|cnpj|cep|telefone"`; a máscara de CNPJ aceita letras); erros ao lado do campo; inativar pedindo confirmação com `dialogo.html`.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: cadastro e busca de clientes"`

### Tarefa 11: Produtos

**Files:**
- Modify: `apps/cadastros/models.py`, `apps/cadastros/forms.py`, `apps/cadastros/views.py`, `apps/cadastros/urls.py`, `apps/cadastros/buscas.py`, `apps/cadastros/admin.py`, `tests/apoio.py`, `tests/seguranca/test_permissoes.py`
- Create: a migração do `Produto`, `templates/cadastros/produtos.html` (com o partial `resultados`), `templates/cadastros/produto_form.html`, `tests/cadastros/test_produtos.py`, `tests/cadastros/test_busca_produtos.py`, `tests/seguranca/test_sem_custo.py`

**Interfaces:**
- Produces:
  - `Produto`: `codigo` (30, único, gravado sem espaços nas pontas e em maiúsculas), `descricao` (200), `marca` (60), `preco` (`DecimalField(12, 2)`), `custo_medio` (`DecimalField(14, 4)`, padrão 0, `editable=False`), `estoque` (`IntegerField`, padrão 0, `editable=False`), `ativo` e as datas. Restrições `produto_estoque_nao_negativo` (`CHECK estoque >= 0`) e `produto_preco_nao_negativo` (`CHECK preco >= 0`). `history = HistoricalRecords(excluded_fields=["estoque", "custo_medio", "atualizado_em"])`.
  - `buscar_produtos(texto: str, *, incluir_inativos: bool = False, limite: int | None = None) -> QuerySet[Produto]`: procura no `codigo` (`icontains`), na `descricao` e na `marca` (`unaccent__icontains`) e no código sem pontuação (`regexp_replace(codigo, '[^A-Z0-9]', '', 'g')` comparado com o texto normalizado). Ordena por código.
  - Rotas: `cadastros:produtos` (`/produtos/`, todos), `cadastros:produto_novo` (`/produtos/novo/`), `cadastros:produto_editar` (`/produtos/<id>/`), `cadastros:produto_inativar` e `cadastros:produto_reativar` (só Administrador).
  - `tests.apoio.criar_produto(codigo="CE285A", *, descricao="Toner HP 85A Preto", marca="HP", preco="189.90", ativo=True) -> Produto`.
  - `tests/seguranca/test_sem_custo.py`: a fixture `cenario_custo`, que devolve um `SimpleNamespace(produto=...)` com um produto de custo médio 87,6543 e estoque 5 (a Tarefa 18 acrescenta `pedido` e `rascunho`); a lista `PAGINAS` de `(url, htmx)`; e os testes "o Vendedor nunca vê custo" e "o Administrador vê o custo".

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_codigo_em_maiusculas_e_sem_espacos(client_admin):
    client_admin.post("/produtos/novo/", {"codigo": " ce285a ", "descricao": "Toner HP 85A Preto",
                                          "marca": "HP", "preco": "189,90"})
    p = Produto.objects.get()
    assert (p.codigo, p.preco, p.estoque, p.custo_medio) == ("CE285A", Decimal("189.90"), 0, Decimal("0"))

def test_codigo_repetido_em_outra_caixa(client_admin):
    criar_produto("CE285A")
    r = client_admin.post("/produtos/novo/", {"codigo": "ce285a", "descricao": "X", "marca": "HP", "preco": "1"})
    assert "Já existe um produto com este código." in r.content.decode()

def test_banco_barra_estoque_e_preco_negativos(db):
    p = criar_produto()
    with pytest.raises(IntegrityError), transaction.atomic():
        Produto.objects.filter(pk=p.pk).update(estoque=-1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Produto.objects.filter(pk=p.pk).update(preco=Decimal("-0.01"))

def test_estoque_e_custo_nao_mudam_pelo_formulario(client_admin):
    p = criar_produto()
    client_admin.post(f"/produtos/{p.pk}/", {"codigo": "CE285A", "descricao": "Toner HP 85A Preto",
                                             "marca": "HP", "preco": "189,90", "estoque": "99", "custo_medio": "1"})
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio) == (0, Decimal("0"))

def test_vendedor_consulta_mas_nao_edita(client_vendedor):
    assert client_vendedor.get("/produtos/").status_code == 200

def test_mudanca_de_preco_vai_para_o_historico(client_admin, administrador):
    p = criar_produto(preco="179.90")
    client_admin.post(f"/produtos/{p.pk}/", {"codigo": "CE285A", "descricao": p.descricao, "marca": "HP", "preco": "189,90"})
    novo, antigo = p.history.all()[:2]
    assert [(m.field, m.old, m.new) for m in novo.diff_against(antigo).changes] == [
        ("preco", Decimal("179.90"), Decimal("189.90"))]

# tests/cadastros/test_busca_produtos.py
@pytest.mark.parametrize("texto", ["ce285", "CE285A", "hp 85a", "toner hp", "HP"])
def test_busca_de_produto(db, texto):
    p = criar_produto("CE285A")
    criar_produto("TN-1060", descricao="Toner Brother TN-1060", marca="Brother")
    assert list(buscar_produtos(texto)) == [p]

def test_busca_ignora_traco_no_codigo(db):
    p = criar_produto("TN-1060", descricao="Toner Brother TN-1060", marca="Brother")
    assert list(buscar_produtos("tn1060")) == [p]

# tests/seguranca/test_sem_custo.py
PAGINAS = [("/produtos/", True), ("/produtos/{produto}/", False)]  # as próximas tarefas acrescentam as suas

@pytest.mark.parametrize("url,htmx", PAGINAS)
def test_vendedor_nunca_ve_custo(client_vendedor, cenario_custo, url, htmx):
    url = url.format(**{nome: obj.pk for nome, obj in vars(cenario_custo).items()})
    html = client_vendedor.get(url, headers={"HX-Request": "true"} if htmx else {}).content.decode()
    for proibido in ["87,65", "87,6543", "Custo", "custo médio", "Lucro", "Margem"]:
        assert proibido not in html, (url, proibido)

def test_administrador_ve_o_custo(client_admin, cenario_custo):
    assert "R$ 87,65" in client_admin.get("/produtos/", headers={"HX-Request": "true"}).content.decode()

# tests/seguranca/test_permissoes.py
ROTAS_SO_ADMIN += [("get", "/produtos/novo/"), ("post", "/produtos/novo/"), ("post", "/produtos/1/"),
                   ("post", "/produtos/1/inativar/"), ("post", "/produtos/1/reativar/")]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/cadastros tests/seguranca`.
- [ ] **Step 3: Implementar**
  - O `GET /produtos/<id>/` fica aberto a todos, mas mostra só a leitura para o Vendedor; o `POST` exige Administrador (verificação dentro da view, antes de olhar o formulário).
  - A lista segue o padrão P18, com filtro por marca (as marcas existentes) e busca. Colunas: Código, Produto, Marca, Preço e Estoque (selo verde; âmbar se for 3 ou menos; vermelho se for 0), mais "Custo médio" só para o Administrador.
  - O formulário não tem os campos `estoque`, `custo_medio` e `ativo`. O Administrador vê o estoque e o custo médio só para leitura, com a frase "O estoque muda só por movimentos (Estoque → Entrada ou Ajuste)."
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: cadastro e busca de produtos"`

---

## Etapa 4: Estoque

**Ao fim da etapa:** o Administrador lança o estoque inicial, as entradas com custo e os ajustes; o custo médio é calculado sozinho; todos veem o histórico de movimentos.

### Tarefa 12: Movimentos de estoque e custo médio

**Files:**
- Create: `apps/estoque/__init__.py`, `apps/estoque/apps.py`, `apps/estoque/models.py`, `apps/estoque/services.py`, `apps/estoque/admin.py`, `apps/estoque/migrations/0001_initial.py`, `tests/estoque/test_custo_medio.py`, `tests/estoque/test_movimentos.py`
- Modify: `config/settings/base.py` (`apps.estoque`), `tests/apoio.py`

**Interfaces:**
- Consumes: `Produto` (Tarefa 11), `exigir_administrador` (Tarefa 2), `RegraDeNegocio` e `EstoqueInsuficiente` (Tarefa 3) e `arredondar_custo` (Tarefa 4).
- Produces:
  - `MovimentoEstoque`: `produto` (FK, `PROTECT`, `related_name="movimentos"`), `tipo` (`Tipo`: `INICIAL="inicial"` "Estoque inicial", `ENTRADA="entrada"` "Entrada", `SAIDA="saida"` "Saída por pedido", `DEVOLUCAO="devolucao"` "Devolução por cancelamento", `AJUSTE_MAIS="ajuste_mais"` "Ajuste (+)", `AJUSTE_MENOS="ajuste_menos"` "Ajuste (−)"), `quantidade` (`CHECK > 0`), `custo_unitario` (14,4), `estoque_apos`, `custo_medio_apos` (14,4), `usuario` (FK, `PROTECT`), `motivo` (200, a observação da entrada ou o motivo do ajuste) e `criado_em` (com índice). Ordenado por `-criado_em, -id`. A FK `pedido` entra na Tarefa 15.
  - Em `apps.estoque.services`:
    - `novo_custo_medio(estoque_atual: int, custo_atual: Decimal, quantidade: int, custo_entrada: Decimal) -> Decimal`.
    - `registrar_estoque_inicial(*, produto_id: int, quantidade: int, custo_unitario: Decimal, usuario) -> MovimentoEstoque`.
    - `registrar_entrada(*, produto_id: int, quantidade: int, custo_unitario: Decimal, observacao: str, usuario) -> MovimentoEstoque`.
    - `registrar_ajuste(*, produto_id: int, delta: int, motivo: str, usuario) -> MovimentoEstoque`.
    - `_aplicar_movimento(produto: Produto, *, tipo: str, quantidade: int, custo_unitario: Decimal, usuario, motivo: str = "", **extra) -> MovimentoEstoque`: exige o produto já travado na transação atual. Calcula o novo estoque e o novo custo médio (Inicial, Entrada e Devolução entram na média; Saída e os Ajustes não mudam a média; o Ajuste (+) entra pelo custo médio atual); levanta `EstoqueInsuficiente` se o estoque ficaria negativo; grava com `Produto.objects.filter(pk=...).update(estoque=..., custo_medio=...)` (para não gerar histórico do produto) e atualiza a instância.
  - `tests.apoio.com_estoque(produto, quantidade: int, custo: str = "100.00", por=None) -> Produto`: usa o estoque inicial se o produto não tiver movimentos e a entrada (observação "teste") se tiver; devolve o produto recarregado.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.mark.parametrize("estoque,custo,qtd,entrada,esperado", [
    (10, "60", 10, "80", "70.0000"),
    (0, "55.5", 4, "80", "80.0000"),
    (7, "10", 3, "20", "13.0000"),
    (2, "10", 1, "11", "10.3333"),
])
def test_formula_do_custo_medio(estoque, custo, qtd, entrada, esperado):
    assert novo_custo_medio(estoque, Decimal(custo), qtd, Decimal(entrada)) == Decimal(esperado)

def test_estoque_inicial(administrador):
    p = criar_produto()
    m = registrar_estoque_inicial(produto_id=p.pk, quantidade=10, custo_unitario=Decimal("60.00"), usuario=administrador)
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio) == (10, Decimal("60.0000"))
    assert (m.tipo, m.estoque_apos, m.custo_medio_apos, m.usuario) == ("inicial", 10, Decimal("60.0000"), administrador)

def test_estoque_inicial_uma_vez_so(administrador):
    p = com_estoque(criar_produto(), 10, "60.00")
    with pytest.raises(RegraDeNegocio, match="Este produto já tem movimentos. Use Entrada."):
        registrar_estoque_inicial(produto_id=p.pk, quantidade=1, custo_unitario=Decimal("1"), usuario=administrador)

def test_entrada_recalcula_o_custo_medio(administrador):
    p = com_estoque(criar_produto(), 10, "60.00")
    m = registrar_entrada(produto_id=p.pk, quantidade=10, custo_unitario=Decimal("80.00"), observacao="NF 8812", usuario=administrador)
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio, m.motivo) == (20, Decimal("70.0000"), "NF 8812")

@pytest.mark.parametrize("campos,mensagem", [
    ({"observacao": ""}, "Informe a observação (ex.: nº da nota)."),
    ({"custo_unitario": Decimal("0")}, "Informe o custo unitário (maior que zero)."),
    ({"quantidade": 0}, "Informe uma quantidade inteira maior que zero."),
])
def test_entrada_exige_dados(administrador, campos, mensagem):
    p = com_estoque(criar_produto(), 1, "60.00")
    dados = {"produto_id": p.pk, "quantidade": 1, "custo_unitario": Decimal("1"), "observacao": "NF 1", "usuario": administrador} | campos
    with pytest.raises(RegraDeNegocio, match=re.escape(mensagem)):
        registrar_entrada(**dados)

def test_ajuste_negativo_nao_deixa_o_estoque_negativo(administrador):
    p = com_estoque(criar_produto(), 3, "60.00")
    with pytest.raises(EstoqueInsuficiente, match="O estoque atual é 3; o ajuste deixaria o estoque negativo."):
        registrar_ajuste(produto_id=p.pk, delta=-4, motivo="avaria", usuario=administrador)
    registrar_ajuste(produto_id=p.pk, delta=-3, motivo="avaria", usuario=administrador)
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio) == (0, Decimal("60.0000"))  # zerado mantém o último custo

def test_ajuste_positivo_entra_pelo_custo_medio(administrador):
    p = com_estoque(criar_produto(), 10, "60.00")
    m = registrar_ajuste(produto_id=p.pk, delta=2, motivo="contagem", usuario=administrador)
    p.refresh_from_db()
    assert (p.estoque, p.custo_medio, m.tipo, m.custo_unitario) == (12, Decimal("60.0000"), "ajuste_mais", Decimal("60.0000"))

def test_ajuste_positivo_recusado_sem_custo(administrador):
    p = criar_produto()
    with pytest.raises(RegraDeNegocio, match="Este produto ainda não tem custo. Lance o estoque inicial ou uma entrada antes do ajuste."):
        registrar_ajuste(produto_id=p.pk, delta=1, motivo="contagem", usuario=administrador)

def test_ajuste_exige_motivo_e_quantidade(administrador):
    p = com_estoque(criar_produto(), 1, "60.00")
    with pytest.raises(RegraDeNegocio, match="Informe o motivo do ajuste."):
        registrar_ajuste(produto_id=p.pk, delta=1, motivo=" ", usuario=administrador)
    with pytest.raises(RegraDeNegocio, match="Informe uma quantidade inteira maior que zero."):
        registrar_ajuste(produto_id=p.pk, delta=0, motivo="x", usuario=administrador)

def test_vendedor_nao_movimenta(vendedor):
    p = criar_produto()
    with pytest.raises(PermissionDenied):
        registrar_estoque_inicial(produto_id=p.pk, quantidade=1, custo_unitario=Decimal("1"), usuario=vendedor)

def test_movimento_nao_gera_historico_do_produto(administrador):
    p = com_estoque(criar_produto(), 10, "60.00")
    registrar_ajuste(produto_id=p.pk, delta=-1, motivo="avaria", usuario=administrador)
    assert p.history.count() == 1
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/estoque`.
- [ ] **Step 3: Implementar.** Cada serviço público: `exigir_administrador(usuario)`, valida a entrada, abre `transaction.atomic()`, faz `Produto.objects.select_for_update().get(pk=produto_id)` e chama `_aplicar_movimento`.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: movimentos de estoque com custo médio automático"`

### Tarefa 13: Telas de estoque

**Files:**
- Create: `apps/estoque/forms.py`, `apps/estoque/views.py`, `apps/estoque/urls.py`, `templates/estoque/historico.html` (com o partial `resultados`), `templates/estoque/movimento_form.html`, `tests/estoque/test_telas.py`, `tests/e2e/test_estoque.py`
- Modify: `config/urls.py`, `tests/seguranca/test_permissoes.py`, `tests/seguranca/test_sem_custo.py`

**Interfaces:**
- Consumes: os serviços da Tarefa 12 e `intervalo_de_datas` (Tarefa 4).
- Produces: rotas `estoque:historico` (`/estoque/`, todos), `estoque:entrada` (`/estoque/entrada/`), `estoque:inicial` (`/estoque/inicial/`) e `estoque:ajuste` (`/estoque/ajuste/`), estas três só para o Administrador. Os formulários recebem o produto pelo código (`<input list>` com `<datalist>` dos códigos ativos; no estoque inicial, só os produtos sem movimentos), e o código desconhecido dá "Produto não encontrado.". Os valores em dinheiro passam por `ler_decimal_br`.
  - Campos: entrada = `codigo`, `quantidade`, `custo_unitario` e `observacao`; estoque inicial = `codigo`, `quantidade` e `custo_unitario`; ajuste = `codigo`, `sentido` (`mais` ou `menos`), `quantidade`, `motivo` e `confirmar`. Rótulos: "Código do produto", "Quantidade", "Custo unitário", "Observação" e "Motivo"; botão "Registrar". Links da tela de histórico: "+ Entrada", "Estoque inicial" e "Ajuste". Lista vazia: "Nenhum movimento no período."

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_registrar_entrada_pela_tela(client_admin):
    p = com_estoque(criar_produto(), 10, "60.00")
    r = client_admin.post("/estoque/entrada/", {"codigo": "ce285a", "quantidade": "20", "custo_unitario": "80,00", "observacao": "NF 8812"})
    assert r["Location"] == "/estoque/"
    p.refresh_from_db()
    assert p.estoque == 30

def test_regra_violada_aparece_no_formulario(client_admin):
    criar_produto()
    r = client_admin.post("/estoque/ajuste/", {"codigo": "CE285A", "sentido": "mais", "quantidade": "1",
                                               "motivo": "contagem", "confirmar": "1"})
    assert "Este produto ainda não tem custo" in r.content.decode()

def test_ajuste_pede_confirmacao(client_admin):
    p = com_estoque(criar_produto(), 5, "60.00")
    dados = {"codigo": "CE285A", "sentido": "menos", "quantidade": "1", "motivo": "avaria"}
    r = client_admin.post("/estoque/ajuste/", dados)
    assert "Confirme o ajuste" in r.content.decode() and p.movimentos.count() == 1
    client_admin.post("/estoque/ajuste/", dados | {"confirmar": "1"})
    assert p.movimentos.count() == 2

def test_historico_filtra_por_produto_e_periodo(client_vendedor):
    com_estoque(criar_produto("CE285A"), 5)
    com_estoque(criar_produto("TN-1060", descricao="Toner Brother TN-1060", marca="Brother"), 5)
    dia, ontem = hoje(), hoje() - timedelta(days=1)
    get = lambda q: client_vendedor.get(f"/estoque/?{q}", headers={"HX-Request": "true"}).content.decode()
    html = get(f"produto=CE285A&inicio={dia}&fim={dia}")
    assert "CE285A" in html and "TN-1060" not in html
    assert "Nenhum movimento no período." in get(f"inicio={ontem}&fim={ontem}")

# tests/seguranca/test_permissoes.py
ROTAS_SO_ADMIN += [("get", "/estoque/entrada/"), ("post", "/estoque/entrada/"), ("get", "/estoque/inicial/"),
                   ("post", "/estoque/inicial/"), ("get", "/estoque/ajuste/"), ("post", "/estoque/ajuste/")]
# tests/seguranca/test_sem_custo.py
PAGINAS += [("/estoque/", True)]

# tests/e2e/test_estoque.py
def test_entrada_de_estoque(pagina, live_server, administrador):
    com_estoque(criar_produto(), 10, "60.00", por=administrador)
    entrar(pagina, live_server, administrador)
    pagina.get_by_role("link", name="Estoque").click()
    pagina.get_by_role("link", name="+ Entrada").click()
    pagina.get_by_label("Código do produto").fill("CE285A")
    pagina.get_by_label("Quantidade").fill("20")
    pagina.get_by_label("Custo unitário").fill("80,00")
    pagina.get_by_label("Observação").fill("NF 8812")
    pagina.get_by_role("button", name="Registrar").click()
    expect(pagina.get_by_text("Entrada · NF 8812")).to_be_visible()
    expect(pagina.get_by_text("+20")).to_be_visible()
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/estoque && uv run pytest -m e2e`.
- [ ] **Step 3: Implementar**
  - Histórico (padrão P18; filtros de produto, tipo e período, padrão últimos 30 dias; 50 por página). Colunas como em `telas.html`: Data (`data_hora_br`), Produto (código), Tipo (selo com detalhe: "Saída · pedido nº 1.042", "Entrada · NF 8812", "Ajuste · avaria"), Qtd. (+20 ou −12) e Por (primeiro nome), mais "Custo unit." só para o Administrador. Botões "Ajuste", "+ Entrada" e "Estoque inicial" só para o Administrador.
  - Ajuste em duas etapas, sem JS: o primeiro POST valida e mostra "Confirme o ajuste: −1 em TN-1060 (motivo: avaria)" com os mesmos dados escondidos e `confirmar=1`; o segundo grava.
  - Depois de gravar, redireciona para `/estoque/` com o aviso "Entrada registrada: CE285A +20" (ou o equivalente). Uma `RegraDeNegocio` aparece como erro geral do formulário.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` e `uv run pytest -m e2e`.
- [ ] **Step 5: Commit.** `git commit -m "feat: telas de estoque com entrada, estoque inicial e ajuste"`

---

## Etapa 5: Pedidos

**Ao fim da etapa:** o fluxo principal funciona de ponta a ponta. A pessoa monta o rascunho com busca, confirma (com estoque e total corretos, inclusive com acessos simultâneos), gera o PDF, cancela e repete pedidos, e o Início mostra os números do mês.

### Tarefa 14: Cálculo de totais, desconto e rateio

**Files:**
- Create: `apps/pedidos/__init__.py`, `apps/pedidos/apps.py`, `apps/pedidos/calculos.py`, `tests/pedidos/test_calculos.py`
- Modify: `config/settings/base.py` (`apps.pedidos`)

**Interfaces:**
- Consumes: `arredondar` e `CENTAVO` (Tarefa 4).
- Produces (em `apps.pedidos.calculos`, funções puras, sem banco):
  - `DESCONTO_REAIS = "reais"` e `DESCONTO_PERCENTUAL = "percentual"`.
  - `Linha(quantidade: int, preco_unitario: Decimal)` (dataclass congelada), com a propriedade `total -> Decimal`.
  - `Totais(subtotal: Decimal, desconto_valor: Decimal, total: Decimal, erro_desconto: str | None)` (dataclass congelada).
  - `calcular_totais(linhas: Sequence[Linha], desconto_tipo: str, desconto_informado: Decimal) -> Totais`. As mensagens de erro são "O desconto não pode ser negativo.", "O desconto não pode passar de 100%." e "O desconto não pode passar do subtotal.". Com erro, o desconto vale 0. Com subtotal 0, o desconto vale 0 e não há erro.
  - `ratear_desconto(totais_itens: Sequence[Decimal], desconto: Decimal) -> list[Decimal]`: levanta `ValueError` se o desconto for negativo ou maior que a soma.
  - `margem(lucro: Decimal, receita: Decimal) -> Decimal | None`: com 4 casas; `None` quando a receita é 0 ou menor.

- [ ] **Step 1: Escrever os testes que falham**

```python
L = lambda *pares: [Linha(q, Decimal(p)) for q, p in pares]

def test_totais_com_percentual():
    assert calcular_totais(L((2, "189.90"), (3, "89.90")), "percentual", Decimal("10")) == Totais(
        Decimal("649.50"), Decimal("64.95"), Decimal("584.55"), None)

def test_percentual_arredonda_meio_para_cima():
    assert calcular_totais(L((1, "649.50")), "percentual", Decimal("33.333")).desconto_valor == Decimal("216.50")
    assert calcular_totais(L((1, "0.05")), "percentual", Decimal("50")).desconto_valor == Decimal("0.03")

def test_desconto_em_reais_ate_o_subtotal():
    assert calcular_totais(L((1, "649.50")), "reais", Decimal("649.50")).total == Decimal("0.00")
    t = calcular_totais(L((1, "649.50")), "reais", Decimal("649.51"))
    assert (t.desconto_valor, t.total, t.erro_desconto) == (Decimal("0"), Decimal("649.50"), "O desconto não pode passar do subtotal.")

def test_erros_de_desconto():
    assert calcular_totais(L((1, "10")), "percentual", Decimal("100.01")).erro_desconto == "O desconto não pode passar de 100%."
    assert calcular_totais(L((1, "10")), "reais", Decimal("-1")).erro_desconto == "O desconto não pode ser negativo."

def test_pedido_vazio_nao_mostra_erro_de_desconto():
    assert calcular_totais([], "reais", Decimal("10")) == Totais(Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), None)

def test_rateio_proporcional():
    assert ratear_desconto([Decimal("200.00"), Decimal("50.00")], Decimal("25.00")) == [Decimal("20.00"), Decimal("5.00")]
    assert sum(ratear_desconto([Decimal("33.33"), Decimal("33.33"), Decimal("33.34")], Decimal("10.00"))) == Decimal("10.00")
    assert ratear_desconto([Decimal("0.00"), Decimal("0.00")], Decimal("0.00")) == [Decimal("0.00"), Decimal("0.00")]

def test_rateio_nunca_negativo_nem_maior_que_o_item():
    rnd = random.Random(42)
    for _ in range(500):
        itens = [Decimal(rnd.randint(1, 50000)) / 100 for _ in range(rnd.randint(1, 8))]
        desconto = Decimal(rnd.randint(0, int(sum(itens) * 100))) / 100
        partes = ratear_desconto(itens, desconto)
        assert sum(partes) == desconto and all(Decimal(0) <= p <= t for p, t in zip(partes, itens, strict=True))
    assert ratear_desconto([Decimal("0.01")] * 4, Decimal("0.02")) == [Decimal("0.01"), Decimal("0.00"), Decimal("0.01"), Decimal("0.00")]

def test_margem():
    assert margem(Decimal("125.00"), Decimal("325.00")) == Decimal("0.3846")
    assert margem(Decimal("-10"), Decimal("100")) == Decimal("-0.1000")
    assert margem(Decimal("0"), Decimal("0")) is None
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/pedidos/test_calculos.py`.
- [ ] **Step 3: Implementar.** O rateio usa arredondamento acumulado (P4):

```python
subtotal = sum(totais_itens, Decimal("0"))
acumulado, distribuido, partes = Decimal("0"), Decimal("0.00"), []
for total in totais_itens:
    acumulado += total
    alvo = arredondar(desconto * acumulado / subtotal) if subtotal else Decimal("0.00")
    partes.append(alvo - distribuido)
    distribuido = alvo
return partes
```

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest tests/pedidos`.
- [ ] **Step 5: Commit.** `git commit -m "feat: cálculo de totais, desconto e rateio do pedido"`

### Tarefa 15: Pedido, itens e rascunho

**Files:**
- Create: `apps/pedidos/models.py`, `apps/pedidos/services.py`, `apps/pedidos/consultas.py`, `apps/pedidos/admin.py`, `apps/pedidos/migrations/0001_initial.py`, `apps/pedidos/migrations/0002_contador.py` (cria `ContadorPedido(id=1, ultimo_numero=0)`), `apps/estoque/migrations/0002_movimento_pedido.py`, `tests/pedidos/test_rascunho.py`, `tests/pedidos/test_rascunho_concorrencia.py`
- Modify: `apps/estoque/models.py` (FK `pedido`), `tests/apoio.py`

**Interfaces:**
- Consumes: `calcular_totais` e `Linha` (Tarefa 14), `Cliente` e `Produto` (Tarefas 10 e 11) e `RegraDeNegocio`, `EstoqueInsuficiente` e `eh_administrador`.
- Produces:
  - `Pedido`: `numero` (inteiro positivo, nulo, único), `status` (`Status`: `RASCUNHO="rascunho"`, `CONFIRMADO="confirmado"`, `CANCELADO="cancelado"`), `cliente` (FK nula, `PROTECT`), `criado_por` (`PROTECT`), `criado_em`, `atualizado_em`, `confirmado_por` e `confirmado_em` (nulos), `cancelado_por` e `cancelado_em` (nulos), `motivo_cancelamento`, `desconto_tipo` (padrão `"percentual"`, como no esboço), `desconto_informado`, `desconto_valor`, `subtotal` e `total` (todos `(12, 2)`, padrão 0) e `observacoes`. Restrições: `pedido_numero_so_fora_do_rascunho` (`(status='rascunho' AND numero IS NULL) OR (status<>'rascunho' AND numero IS NOT NULL)`) e `pedido_valores_nao_negativos`. Índices em `(status, confirmado_em)` e `criado_por`.
  - `ItemPedido`: `pedido` (FK, `CASCADE`, `related_name="itens"`), `produto` (`PROTECT`), `codigo`, `descricao`, `quantidade` (`CHECK > 0`), `preco_unitario` (12,2), `custo_unitario` (14,4, nulo até a confirmação) e `desconto_rateado` (12,2, padrão 0). Restrição `item_produto_unico_no_pedido` em `(pedido, produto)`. Propriedade `total`. Ordenado por `id`.
  - `ContadorPedido`: `ultimo_numero`, com `CHECK id = 1`.
  - `MovimentoEstoque.pedido`: FK nula para `Pedido`, `PROTECT`, `related_name="movimentos"`.
  - Em `apps.pedidos.services`:
    - `QUANTIDADE_MAXIMA = 9999`.
    - `pode_editar(pedido: Pedido, usuario) -> bool`: verdadeiro se for rascunho e o usuário for quem o criou ou um Administrador.
    - `criar_rascunho(usuario) -> Pedido`.
    - `definir_cliente(pedido_id: int, cliente_id: int, usuario) -> Pedido`.
    - `adicionar_item(pedido_id: int, produto_id: int, quantidade: int, usuario) -> ItemPedido`.
    - `alterar_quantidade(pedido_id: int, item_id: int, quantidade: int, usuario) -> ItemPedido`.
    - `remover_item(pedido_id: int, item_id: int, usuario) -> None`.
    - `definir_desconto(pedido_id: int, tipo: str, valor: Decimal, usuario) -> Pedido`.
    - `definir_observacoes(pedido_id: int, texto: str, usuario) -> Pedido`.
    - `excluir_rascunho(pedido_id: int, usuario) -> None`.
    - Internos: `_rascunho_para_editar(pedido_id, usuario) -> Pedido` (faz `select_for_update`; se não for rascunho, levanta `RegraDeNegocio("Este pedido não é mais um rascunho e não pode ser alterado.")`; sem permissão, `PermissionDenied`) e `_recalcular(pedido) -> Totais` (grava `subtotal`, `desconto_valor` e `total`).
  - Em `apps.pedidos.consultas`: `Avisos(gerais: list[str], por_item: dict[int, str], erro_desconto: str | None)` e `avisos_do_rascunho(pedido: Pedido) -> Avisos`.
  - Em `tests.apoio`:
    - `montar_rascunho(usuario, *, cliente=None, itens=(), desconto=None) -> Pedido`, usando os serviços acima. `itens` é uma lista de `(produto, quantidade)` e `desconto` é um par `(tipo, "valor")`. Sem `cliente`, o rascunho fica sem cliente.
    - `rodar_juntos(*funcoes) -> list[object]`: roda cada função numa thread, liberando todas juntas com `threading.Barrier`, e devolve o resultado ou a exceção de cada uma, na ordem. Cada thread chama `connection.close()` no fim.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_rascunho_nasce_sem_numero(vendedor):
    p = criar_rascunho(vendedor)
    assert (p.status, p.numero, p.criado_por, p.total) == ("rascunho", None, vendedor, Decimal("0"))

def test_adicionar_copia_dados_e_soma_na_mesma_linha(vendedor):
    prod = com_estoque(criar_produto(preco="189.90"), 12)
    p = criar_rascunho(vendedor)
    adicionar_item(p.pk, prod.pk, 2, vendedor)
    item = adicionar_item(p.pk, prod.pk, 3, vendedor)
    assert p.itens.count() == 1 and item.quantidade == 5
    assert (item.codigo, item.descricao, item.preco_unitario) == ("CE285A", "Toner HP 85A Preto", Decimal("189.90"))
    p.refresh_from_db()
    assert p.subtotal == Decimal("949.50") and p.total == Decimal("949.50")

def test_nao_adiciona_alem_do_estoque(vendedor):
    prod = com_estoque(criar_produto(), 12)
    p = criar_rascunho(vendedor)
    adicionar_item(p.pk, prod.pk, 10, vendedor)
    with pytest.raises(EstoqueInsuficiente, match=re.escape(
            "Estoque insuficiente: 12 em estoque, 10 já no pedido (dá para adicionar mais 2).")):
        adicionar_item(p.pk, prod.pk, 3, vendedor)

@pytest.mark.parametrize("qtd,mensagem", [(0, "Informe uma quantidade inteira maior que zero."),
                                           (10000, "Quantidade máxima por item: 9.999.")])
def test_quantidade_fora_da_faixa(vendedor, qtd, mensagem):
    prod = com_estoque(criar_produto(), 20000)
    with pytest.raises(RegraDeNegocio, match=re.escape(mensagem)):
        adicionar_item(criar_rascunho(vendedor).pk, prod.pk, qtd, vendedor)

def test_produto_e_cliente_inativos_nao_entram(vendedor):
    prod = criar_produto(ativo=False)
    p = criar_rascunho(vendedor)
    with pytest.raises(RegraDeNegocio, match="Este produto está inativo e não pode ser adicionado."):
        adicionar_item(p.pk, prod.pk, 1, vendedor)
    with pytest.raises(RegraDeNegocio, match="Este cliente está inativo. Escolha outro cliente."):
        definir_cliente(p.pk, criar_cliente(ativo=False).pk, vendedor)

def test_aumentar_quantidade_respeita_o_estoque(vendedor):
    prod = com_estoque(criar_produto(), 3)
    p = montar_rascunho(vendedor, itens=[(prod, 3)])
    item = p.itens.get()
    with pytest.raises(EstoqueInsuficiente, match="Estoque insuficiente para CE285A: 3 em estoque."):
        alterar_quantidade(p.pk, item.pk, 4, vendedor)
    assert alterar_quantidade(p.pk, item.pk, 1, vendedor).quantidade == 1

def test_remover_item_que_deixa_desconto_maior_que_o_subtotal(vendedor):  # Review Focus 4
    a, b = com_estoque(criar_produto("CE285A", preco="189.90"), 5), com_estoque(criar_produto("TN-1060", preco="89.90"), 5)
    p = montar_rascunho(vendedor, itens=[(a, 1), (b, 1)], desconto=("reais", "100"))
    remover_item(p.pk, p.itens.get(produto=a).pk, vendedor)
    p.refresh_from_db()
    assert (p.desconto_informado, p.desconto_valor, p.total) == (Decimal("100.00"), Decimal("0.00"), Decimal("89.90"))
    assert avisos_do_rascunho(p).erro_desconto == "O desconto não pode passar do subtotal."

def test_avisos_de_estoque_e_de_inativos(vendedor):
    prod = com_estoque(criar_produto(), 5)
    cli = criar_cliente()
    p = montar_rascunho(vendedor, cliente=cli, itens=[(prod, 5)])
    Produto.objects.filter(pk=prod.pk).update(estoque=3)
    Cliente.objects.filter(pk=cli.pk).update(ativo=False)
    av = avisos_do_rascunho(p)
    assert av.por_item[p.itens.get().pk] == "Só há 3 em estoque."
    assert av.gerais == ["O cliente Papelaria Central Ltda foi inativado. Escolha outro cliente."]

def test_desconto_invalido_nao_grava(vendedor):
    p = criar_rascunho(vendedor)
    with pytest.raises(RegraDeNegocio, match="O desconto não pode passar de 100%."):
        definir_desconto(p.pk, "percentual", Decimal("101"), vendedor)

def test_so_quem_criou_ou_administrador_edita(vendedor, administrador):
    p = criar_rascunho(vendedor)
    outro = criar_usuario(email="outro@helptoner.com.br")
    with pytest.raises(PermissionDenied):
        definir_observacoes(p.pk, "x", outro)
    assert definir_observacoes(p.pk, "entregar na portaria", administrador).observacoes == "entregar na portaria"
    with pytest.raises(RegraDeNegocio, match="As observações podem ter até 1.000 caracteres."):
        definir_observacoes(p.pk, "x" * 1001, vendedor)

def test_excluir_rascunho(vendedor):
    p = criar_rascunho(vendedor)
    excluir_rascunho(p.pk, vendedor)
    assert not Pedido.objects.filter(pk=p.pk).exists()

# tests/pedidos/test_rascunho_concorrencia.py
@pytest.mark.django_db(transaction=True)
def test_mesmo_produto_em_duas_abas_soma_na_linha():  # Review Focus 2
    vendedor = criar_usuario()
    prod = com_estoque(criar_produto(), 10)
    p = criar_rascunho(vendedor)
    resultados = rodar_juntos(lambda: adicionar_item(p.pk, prod.pk, 2, vendedor),
                              lambda: adicionar_item(p.pk, prod.pk, 3, vendedor))
    assert not any(isinstance(r, Exception) for r in resultados)
    assert p.itens.get().quantidade == 5
```

(O teste que tenta confirmar pedido já confirmado vem na Tarefa 16.)

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/pedidos`.
- [ ] **Step 3: Implementar.** Todo serviço de edição: abre `transaction.atomic()`, chama `_rascunho_para_editar` (a trava na linha do pedido serializa as abas) e, quando algo muda no valor, `_recalcular`. Para somar na mesma linha, procura o item existente com `select_for_update` dentro da trava do pedido. O estoque disponível para adicionar é `produto.estoque` menos a quantidade que o pedido já tem.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: pedido em rascunho com itens, desconto e observações"`

### Tarefa 16: Confirmação do pedido

**Files:**
- Modify: `apps/pedidos/services.py`, `apps/estoque/services.py`, `tests/apoio.py`
- Create: `tests/pedidos/test_confirmacao.py`, `tests/pedidos/test_confirmacao_concorrencia.py`

**Interfaces:**
- Consumes: `ratear_desconto` (Tarefa 14), `_rascunho_para_editar` e `_recalcular` (Tarefa 15) e `_aplicar_movimento` (Tarefa 12).
- Produces:
  - `MudancaPreco(codigo: str, descricao: str, preco_anterior: Decimal, preco_novo: Decimal)` (dataclass congelada).
  - `ConfirmacaoRecusada(RegraDeNegocio)`, com `motivos: list[str]` (a mensagem junta os motivos com espaço).
  - `PrecosAlterados(RegraDeNegocio)`, com `mudancas: list[MudancaPreco]` e a mensagem "Os preços de alguns produtos mudaram. Confira o novo total e confirme de novo."
  - `confirmar_pedido(pedido_id: int, usuario) -> Pedido`.
  - Em `apps.estoque.services`: `registrar_saida_pedido(*, produto: Produto, quantidade: int, pedido: Pedido, usuario) -> MovimentoEstoque` (o produto já vem travado).
  - `tests.apoio.montar_pedido_confirmado(usuario, *, cliente=None, itens, desconto=None) -> Pedido`: monta o rascunho e confirma. Sem `cliente`, cria um com `criar_cliente()`.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.fixture
def dois_produtos(administrador):
    return (com_estoque(criar_produto("CE285A", preco="100.00"), 10, "60.00", por=administrador),
            com_estoque(criar_produto("TN-1060", descricao="Toner Brother TN-1060", marca="Brother", preco="50.00"), 10, "20.00", por=administrador))

def test_confirmar_grava_numero_custo_baixa_rateio_e_totais(vendedor, dois_produtos):
    p1, p2 = dois_produtos
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(p1, 2), (p2, 1)], desconto=("percentual", "10"))
    ped = confirmar_pedido(ped.pk, vendedor)
    assert (ped.numero, ped.status, ped.confirmado_por) == (1, "confirmado", vendedor) and ped.confirmado_em
    assert (ped.subtotal, ped.desconto_valor, ped.total) == (Decimal("250.00"), Decimal("25.00"), Decimal("225.00"))
    i1, i2 = ped.itens.order_by("id")
    assert (i1.custo_unitario, i1.desconto_rateado, i2.desconto_rateado) == (Decimal("60.0000"), Decimal("20.00"), Decimal("5.00"))
    p1.refresh_from_db()
    saida = MovimentoEstoque.objects.get(produto=p1, tipo="saida")
    assert (p1.estoque, saida.quantidade, saida.pedido, saida.estoque_apos, saida.custo_unitario) == (
        8, 2, ped, 8, Decimal("60.0000"))

def test_numeracao_sem_buracos(vendedor, dois_produtos):
    p1, _ = dois_produtos
    cli = criar_cliente()
    assert confirmar_pedido(montar_rascunho(vendedor, cliente=cli, itens=[(p1, 1)]).pk, vendedor).numero == 1
    falha = montar_rascunho(vendedor, cliente=cli, itens=[(p1, 1)])
    Produto.objects.filter(pk=p1.pk).update(estoque=0)
    with pytest.raises(ConfirmacaoRecusada):
        confirmar_pedido(falha.pk, vendedor)
    Produto.objects.filter(pk=p1.pk).update(estoque=5)
    assert confirmar_pedido(falha.pk, vendedor).numero == 2
    assert ContadorPedido.objects.get().ultimo_numero == 2

def test_preco_alterado_atualiza_o_rascunho_e_nao_confirma(vendedor):
    prod = com_estoque(criar_produto(preco="179.90"), 10)
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(prod, 1)])
    prod.preco = Decimal("189.90")
    prod.save()
    with pytest.raises(PrecosAlterados) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.mudancas == [MudancaPreco("CE285A", "Toner HP 85A Preto", Decimal("179.90"), Decimal("189.90"))]
    ped.refresh_from_db()
    prod.refresh_from_db()
    assert (ped.status, ped.numero, ped.subtotal, ped.itens.get().preco_unitario, prod.estoque) == (
        "rascunho", None, Decimal("189.90"), Decimal("189.90"), 10)
    assert confirmar_pedido(ped.pk, vendedor).numero == 1

def test_preco_menor_que_deixa_o_desconto_maior_que_o_subtotal(vendedor):  # Review Focus 4
    prod = com_estoque(criar_produto(preco="179.90"), 10)
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(prod, 1)], desconto=("reais", "150"))
    Produto.objects.filter(pk=prod.pk).update(preco=Decimal("100.00"))
    with pytest.raises(PrecosAlterados):
        confirmar_pedido(ped.pk, vendedor)
    with pytest.raises(ConfirmacaoRecusada, match="O desconto não pode passar do subtotal."):
        confirmar_pedido(ped.pk, vendedor)

@pytest.mark.parametrize("cenario,motivo", [
    ("cliente_inativo", "O cliente Papelaria Central Ltda foi inativado. Escolha outro cliente."),
    ("produto_inativo", "O produto CE285A foi inativado. Remova-o do pedido."),
    ("sem_cliente", "Escolha o cliente antes de confirmar."),
    ("sem_itens", "Adicione pelo menos um produto."),
    ("sem_estoque", "Estoque insuficiente para CE285A: 2 em estoque, 8 no pedido."),
])
def test_confirmacao_recusada_nao_muda_nada(vendedor, cenario, motivo):
    prod = com_estoque(criar_produto(), 10)
    cli = criar_cliente("Papelaria Central Ltda")
    ped = montar_rascunho(vendedor, cliente=cli, itens=[(prod, 8)])
    match cenario:
        case "cliente_inativo": Cliente.objects.filter(pk=cli.pk).update(ativo=False)
        case "produto_inativo": Produto.objects.filter(pk=prod.pk).update(ativo=False)
        case "sem_cliente": Pedido.objects.filter(pk=ped.pk).update(cliente=None)
        case "sem_itens": ped.itens.all().delete()
        case "sem_estoque": Produto.objects.filter(pk=prod.pk).update(estoque=2)
    estoque_antes = Produto.objects.get(pk=prod.pk).estoque
    with pytest.raises(ConfirmacaoRecusada) as erro:
        confirmar_pedido(ped.pk, vendedor)
    assert erro.value.motivos == [motivo]
    ped.refresh_from_db()
    assert (ped.status, ped.numero) == ("rascunho", None)
    assert Produto.objects.get(pk=prod.pk).estoque == estoque_antes and ContadorPedido.objects.get().ultimo_numero == 0
    assert not MovimentoEstoque.objects.filter(tipo="saida").exists()

def test_vendedor_nao_confirma_rascunho_de_outro(vendedor, administrador):
    prod = com_estoque(criar_produto(), 5)
    outro = criar_usuario(email="outro@helptoner.com.br")
    ped = montar_rascunho(outro, cliente=criar_cliente(), itens=[(prod, 1)])
    with pytest.raises(PermissionDenied):
        confirmar_pedido(ped.pk, vendedor)
    ped = confirmar_pedido(ped.pk, administrador)
    assert (ped.criado_por, ped.confirmado_por) == (outro, administrador)

# tests/pedidos/test_confirmacao_concorrencia.py
@pytest.mark.django_db(transaction=True)
def test_duas_confirmacoes_disputando_o_estoque():
    v = criar_usuario()
    prod = com_estoque(criar_produto(), 10)
    cli = criar_cliente()
    a, b = (montar_rascunho(v, cliente=cli, itens=[(prod, 8)]) for _ in range(2))
    resultados = rodar_juntos(lambda: confirmar_pedido(a.pk, v), lambda: confirmar_pedido(b.pk, v))
    recusas = [r for r in resultados if isinstance(r, ConfirmacaoRecusada)]
    assert len(recusas) == 1 and recusas[0].motivos == ["Estoque insuficiente para CE285A: 2 em estoque, 8 no pedido."]
    prod.refresh_from_db()
    assert prod.estoque == 2 and ContadorPedido.objects.get().ultimo_numero == 1

@pytest.mark.django_db(transaction=True)
def test_mesmo_rascunho_confirmado_duas_vezes_ao_mesmo_tempo():  # Review Focus 2
    v = criar_usuario()
    prod = com_estoque(criar_produto(), 10)
    ped = montar_rascunho(v, cliente=criar_cliente(), itens=[(prod, 1)])
    resultados = rodar_juntos(lambda: confirmar_pedido(ped.pk, v), lambda: confirmar_pedido(ped.pk, v))
    assert sum(isinstance(r, Pedido) for r in resultados) == 1
    assert any(isinstance(r, RegraDeNegocio) and "não é mais um rascunho" in r.mensagem for r in resultados)
    assert MovimentoEstoque.objects.filter(tipo="saida").count() == 1 and ContadorPedido.objects.get().ultimo_numero == 1
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/pedidos`.
- [ ] **Step 3: Implementar** `confirmar_pedido`, seguindo a ordem de §3.1. As alterações de preço precisam ser gravadas **sem** confirmar o pedido, e por isso a exceção sai depois do bloco atômico:

```
with transaction.atomic():
    pedido = _rascunho_para_editar(pedido_id, usuario)
    se não tem cliente ou não tem itens → ConfirmacaoRecusada (nada mudou)
    itens = itens ordenados por produto_id
    produtos = Produto.objects.select_for_update().filter(pk__in=...).order_by("pk")   # 1. trava, em ordem de id
    motivos = cliente inativo + produtos inativos                                         # 2.
    se motivos → ConfirmacaoRecusada(motivos)
    mudancas = itens cujo preco_unitario != produto.preco                                 # 3.
    se mudancas: atualiza preco_unitario dos itens e _recalcular(pedido)   (sai do bloco sem exceção → grava)
    senão:
        totais = _recalcular(pedido); se totais.erro_desconto → ConfirmacaoRecusada([erro])
        faltas = itens com quantidade > produto.estoque → ConfirmacaoRecusada(faltas)     # 4.
        contador = ContadorPedido.objects.select_for_update().get(pk=1); +1               # 5.
        para cada item: custo_unitario = produto.custo_medio; registrar_saida_pedido     # 6. e 7.
        desconto_rateado = ratear_desconto(...); bulk_update dos itens
        numero, status, confirmado_por e confirmado_em = agora; save                      # 8.
se mudancas: raise PrecosAlterados(mudancas)
```

- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: confirmação do pedido com numeração, baixa de estoque e travas"`

### Tarefa 17: Cancelamento e "Repetir pedido"

**Files:**
- Modify: `apps/pedidos/services.py`, `apps/estoque/services.py`
- Create: `tests/pedidos/test_cancelamento.py`, `tests/pedidos/test_repetir.py`

**Interfaces:**
- Consumes: `_aplicar_movimento` (Tarefa 12), `criar_rascunho` (Tarefa 15) e `montar_pedido_confirmado` (Tarefa 16).
- Produces:
  - `cancelar_pedido(pedido_id: int, motivo: str, usuario) -> Pedido`: exige Administrador. Trava o pedido e depois os produtos, em ordem de id. As mensagens são "Informe o motivo do cancelamento." e "Só pedidos confirmados podem ser cancelados.".
  - `repetir_pedido(pedido_id: int, usuario) -> Pedido`: aberto a todos. A mensagem de recusa é "Só pedidos confirmados ou cancelados podem ser repetidos.".
  - Em `apps.estoque.services`: `registrar_devolucao_pedido(*, produto: Produto, quantidade: int, custo_unitario: Decimal, pedido: Pedido, usuario) -> MovimentoEstoque`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_cancelar_devolve_o_estoque_pelo_custo_gravado(administrador, vendedor):
    prod = com_estoque(criar_produto(), 10, "60.00", por=administrador)
    ped = montar_pedido_confirmado(vendedor, itens=[(prod, 2)])           # sai com custo 60
    registrar_entrada(produto_id=prod.pk, quantidade=8, custo_unitario=Decimal("80.00"), observacao="NF 9", usuario=administrador)
    ped = cancelar_pedido(ped.pk, "Cliente desistiu", administrador)     # estoque 16 a 70,0000
    prod.refresh_from_db()
    assert (prod.estoque, prod.custo_medio) == (18, Decimal("68.8889"))  # (16×70 + 2×60) ÷ 18
    assert (ped.status, ped.cancelado_por, ped.motivo_cancelamento) == ("cancelado", administrador, "Cliente desistiu")
    dev = MovimentoEstoque.objects.get(tipo="devolucao")
    assert (dev.quantidade, dev.custo_unitario, dev.pedido) == (2, Decimal("60.0000"), ped)

def test_cancelamento_exige_administrador_motivo_e_pedido_confirmado(vendedor, administrador):
    prod = com_estoque(criar_produto(), 10)
    ped = montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    with pytest.raises(PermissionDenied):
        cancelar_pedido(ped.pk, "x", vendedor)
    with pytest.raises(RegraDeNegocio, match="Informe o motivo do cancelamento."):
        cancelar_pedido(ped.pk, "  ", administrador)
    with pytest.raises(RegraDeNegocio, match="Só pedidos confirmados podem ser cancelados."):
        cancelar_pedido(criar_rascunho(vendedor).pk, "x", administrador)

@pytest.mark.django_db(transaction=True)
def test_cancelar_duas_vezes_ao_mesmo_tempo_devolve_uma_vez():  # Review Focus 2
    adm = criar_usuario(ADMINISTRADOR)
    prod = com_estoque(criar_produto(), 10, por=adm)
    ped = montar_pedido_confirmado(adm, itens=[(prod, 2)])
    rodar_juntos(lambda: cancelar_pedido(ped.pk, "a", adm), lambda: cancelar_pedido(ped.pk, "b", adm))
    prod.refresh_from_db()
    assert prod.estoque == 10 and MovimentoEstoque.objects.filter(tipo="devolucao").count() == 1

def test_repetir_usa_precos_e_descricoes_atuais(vendedor):
    prod = com_estoque(criar_produto(preco="179.90"), 10)
    original = montar_pedido_confirmado(vendedor, itens=[(prod, 2)], desconto=("percentual", "10"))
    Produto.objects.filter(pk=prod.pk).update(preco=Decimal("189.90"), descricao="Toner HP 85A Preto (novo)")
    outro = criar_usuario(email="outro@helptoner.com.br")
    novo = repetir_pedido(original.pk, outro)
    item = novo.itens.get()
    assert (novo.status, novo.cliente, novo.criado_por, novo.desconto_informado, novo.observacoes) == (
        "rascunho", original.cliente, outro, Decimal("0"), "")
    assert (item.quantidade, item.preco_unitario, item.descricao) == (2, Decimal("189.90"), "Toner HP 85A Preto (novo)")
    assert novo.subtotal == Decimal("379.80")
    original.refresh_from_db()
    assert original.itens.get().preco_unitario == Decimal("179.90")

def test_repetir_funciona_para_cancelado_e_nao_para_rascunho(vendedor, administrador):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    cancelar_pedido(ped.pk, "Cliente desistiu", administrador)
    assert repetir_pedido(ped.pk, vendedor).status == "rascunho"
    with pytest.raises(RegraDeNegocio, match="Só pedidos confirmados ou cancelados podem ser repetidos."):
        repetir_pedido(criar_rascunho(vendedor).pk, vendedor)
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/pedidos`.
- [ ] **Step 3: Implementar.** O repetir chama `criar_rascunho` e, no mesmo bloco atômico, cria os itens com os dados atuais do produto (sem conferir estoque nem se o produto está ativo; os avisos do rascunho mostram isso) e chama `_recalcular`.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: cancelamento com devolução de estoque e repetição de pedido"`

### Tarefa 18: Lista e detalhe dos pedidos

**Files:**
- Create: `apps/pedidos/views.py`, `apps/pedidos/urls.py`, `apps/pedidos/forms.py`, `templates/pedidos/lista.html` (com o partial `resultados`), `templates/pedidos/detalhe.html`, `tests/pedidos/test_lista.py`, `tests/pedidos/test_detalhe.py`
- Modify: `apps/pedidos/consultas.py`, `config/urls.py`, `tests/seguranca/test_permissoes.py`, `tests/seguranca/test_sem_custo.py`

**Interfaces:**
- Consumes: `cancelar_pedido` (Tarefa 17), `intervalo_de_datas` e os formatos (Tarefa 4) e `margem` (Tarefa 14).
- Produces:
  - `filtrar_pedidos(*, busca: str = "", status: str = "", mes: str = "") -> QuerySet[Pedido]`. Se a busca, sem "nº", "n" e pontos, for só dígitos, procura pelo número exato; senão, procura no nome do cliente (`unaccent__icontains`). O `mes` vem como "AAAA-MM", e a data de referência é `Coalesce("confirmado_em", "criado_em")`, comparada com o mês de Brasília. Ordena pela data de referência, do mais recente para o mais antigo, e depois por `-id`.
  - `lucro_do_pedido(pedido: Pedido) -> tuple[Decimal, Decimal | None]`, que devolve o lucro bruto e a margem.
  - Rotas: `pedidos:lista` (`/pedidos/`), `pedidos:detalhe` (`/pedidos/<id>/`) e `pedidos:cancelar` (`/pedidos/<id>/cancelar/`, POST, só Administrador).

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_busca_por_numero_com_ou_sem_ponto(client_vendedor, vendedor):
    ContadorPedido.objects.update(ultimo_numero=1041)
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    for busca in ["1.042", "1042", "nº 1042"]:
        html = client_vendedor.get(f"/pedidos/?busca={busca}", headers={"HX-Request": "true"}).content.decode()
        assert f"/pedidos/{ped.pk}/" in html, busca

def test_busca_por_cliente_sem_acento(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, cliente=criar_cliente("João da Silva", tipo="PF", documento="12345678909"),
                                   itens=[(com_estoque(criar_produto(), 5), 1)])
    assert f"/pedidos/{ped.pk}/" in client_vendedor.get("/pedidos/?busca=joao", headers={"HX-Request": "true"}).content.decode()

def test_filtro_de_mes_no_fuso_de_brasilia(client_vendedor, vendedor):  # Review Focus 3
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    Pedido.objects.filter(pk=ped.pk).update(confirmado_em=datetime(2026, 11, 1, 1, 30, tzinfo=UTC))  # 31/10 22h30
    get = lambda mes: client_vendedor.get(f"/pedidos/?mes={mes}", headers={"HX-Request": "true"}).content.decode()
    assert f"/pedidos/{ped.pk}/" in get("2026-10") and f"/pedidos/{ped.pk}/" not in get("2026-11")

def test_vendedor_ve_todos_os_pedidos_com_quem_emitiu(client_vendedor, administrador):
    montar_pedido_confirmado(administrador, itens=[(com_estoque(criar_produto(), 5), 1)])
    assert "Lucas" in client_vendedor.get("/pedidos/", headers={"HX-Request": "true"}).content.decode()

def test_lista_vazia_e_paginacao(client_vendedor, vendedor):
    assert "Nenhum pedido ainda. Comece um novo pedido." in client_vendedor.get(
        "/pedidos/", headers={"HX-Request": "true"}).content.decode()
    for _ in range(21):
        criar_rascunho(vendedor)
    assert "1–20 de 21" in client_vendedor.get("/pedidos/", headers={"HX-Request": "true"}).content.decode()

def test_detalhe_do_pedido(client_vendedor, vendedor):
    cli = criar_cliente("Papelaria Central Ltda", documento="11222333000181")
    ped = montar_pedido_confirmado(vendedor, cliente=cli, itens=[(com_estoque(criar_produto(preco="100.00"), 5), 2)],
                                   desconto=("percentual", "10"))
    html = client_vendedor.get(f"/pedidos/{ped.pk}/").content.decode()
    for trecho in ["Pedido nº 1", "Confirmado", "11.222.333/0001-81", "Toner HP 85A Preto", "R$ 200,00",
                   "Desconto (10%)", "− R$ 20,00", "R$ 180,00", "Emitido por Carla"]:
        assert trecho in html
    assert "Cancelar pedido" not in html and "Lucro" not in html

def test_administrador_ve_lucro_e_cancela_com_motivo(client_admin, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(preco="100.00"), 5, "60.00"), 1)])
    assert "Lucro bruto R$ 40,00 · margem 40,0%" in client_admin.get(f"/pedidos/{ped.pk}/").content.decode()
    assert "Informe o motivo do cancelamento." in client_admin.post(f"/pedidos/{ped.pk}/cancelar/", {"motivo": ""}, follow=True).content.decode()
    client_admin.post(f"/pedidos/{ped.pk}/cancelar/", {"motivo": "Cliente desistiu"})
    html = client_admin.get(f"/pedidos/{ped.pk}/").content.decode()
    assert "Cancelado por Lucas" in html and "Cliente desistiu" in html

# tests/seguranca/test_permissoes.py
ROTAS_SO_ADMIN += [("post", "/pedidos/1/cancelar/")]
# tests/seguranca/test_sem_custo.py: cenario_custo passa a ter também pedido (confirmado pelo vendedor,
# 1 unidade do produto) e rascunho (do vendedor, com 1 unidade do produto)
PAGINAS += [("/pedidos/{pedido}/", False), ("/pedidos/", True)]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/pedidos tests/seguranca`.
- [ ] **Step 3: Implementar**
  - Lista no padrão P18, com 20 por página: busca "Nº do pedido ou cliente", filtros de status (Todos, Rascunho, Confirmado, Cancelado) e de mês (os últimos 12 meses mais "Todos"). Colunas como em `telas.html`: Nº (ou "—"), Data, Cliente, Emitido por, Total e Status. No celular, as linhas viram cartões. O botão "+ Novo pedido" fica para a Tarefa 19.
  - Detalhe, para todos e em qualquer status: cabeçalho "Pedido nº 1.042" com o selo; dados do cliente; o histórico do pedido ("Emitido por Carla em 02/10/2026 14:35", "Confirmado por …", "Cancelado por Lucas em … · Motivo: …"); itens; subtotal; a linha de desconto ("Desconto (10%)" ou "Desconto", com "− R$ …"); total; observações. Para o Administrador, "Lucro bruto R$ X · margem Y%" e o botão "Cancelar pedido" (só se estiver confirmado), que abre `dialogo.html` com o motivo obrigatório e o texto "O estoque dos N produtos volta.".
  - `cancelar`: se der certo, avisa "Pedido nº 1 cancelado. O estoque voltou." e redireciona para o detalhe. Uma `RegraDeNegocio` vira aviso de erro e redireciona também.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: lista e detalhe dos pedidos com cancelamento"`

### Tarefa 19: Tela do rascunho (novo pedido)

**Files:**
- Create: `templates/pedidos/editor.html` (partials `cliente`, `itens`, `resumo`, `atualizacao`, `sugestoes_cliente` e `sugestoes_produto`), `apps/pedidos/templatetags/__init__.py`, `apps/pedidos/templatetags/pedidos.py`, `static/js/sugestoes.js`, `tests/pedidos/test_editor.py`, `tests/pedidos/test_sugestoes.py`, `tests/pedidos/test_realce.py`
- Modify: `apps/pedidos/views.py`, `apps/pedidos/urls.py`, `apps/pedidos/forms.py`, `templates/pedidos/detalhe.html` (botões "Continuar editando" e "Repetir pedido"), `templates/pedidos/lista.html` (botão "+ Novo pedido"), `static/js/app.js` (animação do total), `tests/seguranca/test_sem_custo.py`

**Interfaces:**
- Consumes: os serviços das Tarefas 15 a 17, `avisos_do_rascunho`, `buscar_clientes` e `buscar_produtos` (com `limite=6`) e `ler_decimal_br`.
- Produces:
  - Rotas, todas com o prefixo `/pedidos/<id>/` e o nome `pedidos:<nome>`:
    - `novo` (`/pedidos/novo/`, POST) e `editar` (`editar/`, GET);
    - `sugestoes_cliente` (`sugestoes/clientes/?q=`) e `sugestoes_produto` (`sugestoes/produtos/?q=`);
    - `definir_cliente` (`cliente/`), `adicionar_item` (`itens/`), `alterar_quantidade` (`itens/<item_id>/quantidade/`, com `quantidade` ou `acao=mais|menos`), `remover_item` (`itens/<item_id>/remover/`), `definir_desconto` (`desconto/`) e `definir_observacoes` (`observacoes/`);
    - `confirmar` (`confirmar/`), `excluir` (`excluir/`) e `repetir` (`repetir/`), todos POST.
  - Filtro `realce(texto: str, busca: str) -> SafeString`: escapa o texto e marca com `<mark>` o primeiro trecho que bate com a busca, sem diferenciar acentos nem maiúsculas. Para isso, mapeia cada caractere original para a sua forma sem acento (NFD sem marcas combinantes, em minúsculas) e procura nessa versão.
  - Formulários: `ItemForm` (`produto_id` e `quantidade`, que precisa casar com `^\d+$` e ficar entre 1 e 9.999, com as mensagens da Tarefa 15) e `DescontoForm` (`tipo` e `valor`, que passa por `ler_decimal_br`; se falhar, "Informe um número. Ex.: 10 ou 10,5").
  - `sugestoes.js`: liga cada `[data-sugestoes]`, que tem um campo `[data-sugestoes-campo]` e uma lista `[role=listbox]`. Quando os resultados chegam, a primeira opção disponível já fica selecionada (como no esboço); as setas movem `aria-selected` entre as opções `[role=option]:not([aria-disabled=true])`; Enter escolhe; Esc fecha; a lista fecha 120 ms depois de o campo perder o foco. Opção de cliente: é um botão com `hx-post` para `definir_cliente`. Opção de produto: preenche o `produto_id` escondido, o texto do campo e a linha de informação ("R$ 189,90 cada · 12 em estoque · 3 já no pedido", via `data-*` e `textContent`) e põe o foco na quantidade.

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.fixture
def rascunho(vendedor):
    return criar_rascunho(vendedor)

def htmx_post(client, url, dados):
    return client.post(url, dados, headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/"})

def test_novo_pedido_abre_o_editor(client_vendedor):
    r = client_vendedor.post("/pedidos/novo/")
    ped = Pedido.objects.get()
    assert r["Location"] == f"/pedidos/{ped.pk}/editar/"
    html = client_vendedor.get(r["Location"]).content.decode()
    assert "Novo pedido" in html and "Rascunho" in html and "Confirmar pedido" in html

def test_adicionar_item_atualiza_itens_e_resumo(client_vendedor, rascunho):
    prod = com_estoque(criar_produto(preco="189.90"), 12)
    html = htmx_post(client_vendedor, f"/pedidos/{rascunho.pk}/itens/", {"produto_id": prod.pk, "quantidade": "2"}).content.decode()
    assert "Toner HP 85A Preto" in html and 'id="resumo"' in html and "hx-swap-oob" in html and "R$ 379,80" in html

@pytest.mark.parametrize("qtd,erro", [("abc", "Informe uma quantidade inteira maior que zero."), ("1,5", "Informe uma quantidade inteira maior que zero."),
                                       ("0", "Informe uma quantidade inteira maior que zero."), ("-1", "Informe uma quantidade inteira maior que zero."),
                                       ("", "Informe uma quantidade inteira maior que zero."), ("10000", "Quantidade máxima por item: 9.999.")])
def test_quantidade_invalida_nao_grava(client_vendedor, rascunho, qtd, erro):
    prod = com_estoque(criar_produto(), 12)
    html = htmx_post(client_vendedor, f"/pedidos/{rascunho.pk}/itens/", {"produto_id": prod.pk, "quantidade": qtd}).content.decode()
    assert erro in html and not rascunho.itens.exists()

def test_estoque_insuficiente_mostra_quanto_ainda_cabe(client_vendedor, rascunho):
    prod = com_estoque(criar_produto(), 12)
    htmx_post(client_vendedor, f"/pedidos/{rascunho.pk}/itens/", {"produto_id": prod.pk, "quantidade": "10"})
    html = htmx_post(client_vendedor, f"/pedidos/{rascunho.pk}/itens/", {"produto_id": prod.pk, "quantidade": "3"}).content.decode()
    assert "dá para adicionar mais 2" in html

def test_desconto_com_virgula_e_texto_invalido(client_vendedor, rascunho):
    htmx_post(client_vendedor, f"/pedidos/{rascunho.pk}/desconto/", {"tipo": "percentual", "valor": "10,5"})
    rascunho.refresh_from_db()
    assert rascunho.desconto_informado == Decimal("10.50")
    html = htmx_post(client_vendedor, f"/pedidos/{rascunho.pk}/desconto/", {"tipo": "percentual", "valor": "abc"}).content.decode()
    assert "Informe um número. Ex.: 10 ou 10,5" in html

def test_desconto_maior_que_o_subtotal_depois_de_remover_item(client_vendedor, vendedor):  # Review Focus 4
    a = com_estoque(criar_produto("CE285A", preco="189.90"), 5)
    b = com_estoque(criar_produto("TN-1060", preco="89.90"), 5)
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(a, 1), (b, 1)], desconto=("reais", "100"))
    html = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/itens/{ped.itens.get(produto=a).pk}/remover/", {}).content.decode()
    assert "O desconto não pode passar do subtotal." in html and "R$ 89,90" in html
    html = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/confirmar/", {}).content.decode()
    assert "O desconto não pode passar do subtotal." in html
    ped.refresh_from_db()
    assert ped.status == "rascunho"

def test_confirmar_vai_para_o_detalhe_com_aviso(client_vendedor, vendedor):
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(com_estoque(criar_produto(), 5), 1)])
    r = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/confirmar/", {})
    assert r["HX-Redirect"] == f"/pedidos/{ped.pk}/"
    assert "Pedido nº 1 confirmado" in client_vendedor.get(f"/pedidos/{ped.pk}/").content.decode()

def test_confirmar_com_preco_alterado_mostra_o_que_mudou(client_vendedor, vendedor):
    prod = com_estoque(criar_produto(preco="179.90"), 5)
    ped = montar_rascunho(vendedor, cliente=criar_cliente(), itens=[(prod, 1)])
    Produto.objects.filter(pk=prod.pk).update(preco=Decimal("189.90"))
    html = htmx_post(client_vendedor, f"/pedidos/{ped.pk}/confirmar/", {}).content.decode()
    assert "CE285A: de R$ 179,90 para R$ 189,90" in html and "confirme de novo" in html

def test_rascunho_de_outra_pessoa(client_vendedor):
    ped = criar_rascunho(criar_usuario(email="outro@helptoner.com.br"))
    assert client_vendedor.get(f"/pedidos/{ped.pk}/editar/")["Location"] == f"/pedidos/{ped.pk}/"
    assert htmx_post(client_vendedor, f"/pedidos/{ped.pk}/observacoes/", {"texto": "x"}).status_code == 403

def test_pedido_confirmado_nao_abre_no_editor(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    assert client_vendedor.get(f"/pedidos/{ped.pk}/editar/")["Location"] == f"/pedidos/{ped.pk}/"

def test_sessao_expirada_no_rascunho_volta_ao_pedido(client, vendedor):  # Review Focus 1
    ped = criar_rascunho(vendedor)
    r = client.post(f"/pedidos/{ped.pk}/itens/", {"produto_id": "1", "quantidade": "1"},
                    headers={"HX-Request": "true", "HX-Current-URL": f"http://testserver/pedidos/{ped.pk}/editar/"})
    assert r["HX-Redirect"] == f"/contas/login/?next=/pedidos/{ped.pk}/editar/"

def test_repetir_abre_o_novo_rascunho(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    r = client_vendedor.post(f"/pedidos/{ped.pk}/repetir/")
    assert r["Location"] == f"/pedidos/{Pedido.objects.latest('pk').pk}/editar/"

# tests/pedidos/test_sugestoes.py
def test_sugestoes_de_cliente_com_realce_e_sem_inativos(client_vendedor, rascunho):
    criar_cliente("João da Silva", tipo="PF", documento="12345678909")
    criar_cliente("Joana Inativa", tipo="PF", ativo=False)
    html = client_vendedor.get(f"/pedidos/{rascunho.pk}/sugestoes/clientes/?q=joao").content.decode()
    assert "<mark>João</mark> da Silva" in html and "Joana" not in html

def test_sugestoes_escapam_html(client_vendedor, rascunho):
    criar_cliente("<b>Bar</b> & Cia")
    html = client_vendedor.get(f"/pedidos/{rascunho.pk}/sugestoes/clientes/?q=bar").content.decode()
    assert "&lt;b&gt;" in html and "<b>Bar" not in html

def test_sugestoes_de_produto_marcam_indisponiveis(client_vendedor, vendedor):
    sem = criar_produto("CF217A", descricao="Toner HP 17A Preto")
    cheio = com_estoque(criar_produto("CE285A"), 3)
    ped = montar_rascunho(vendedor, itens=[(cheio, 3)])
    html = client_vendedor.get(f"/pedidos/{ped.pk}/sugestoes/produtos/?q=toner").content.decode()
    assert "Sem estoque" in html and "Todo no pedido" in html and html.count('aria-disabled="true"') == 2

def test_nada_encontrado(client_vendedor, rascunho):
    assert "Nada encontrado para “zzz”." in client_vendedor.get(f"/pedidos/{rascunho.pk}/sugestoes/produtos/?q=zzz").content.decode()

# tests/pedidos/test_realce.py
def test_realce():
    assert realce("João da Silva", "joao") == "<mark>João</mark> da Silva"
    assert realce("<b>x</b>", "b") == "&lt;<mark>b</mark>&gt;x&lt;/b&gt;"
    assert realce("abc", "") == "abc"

# tests/seguranca/test_sem_custo.py
PAGINAS += [("/pedidos/{rascunho}/editar/", False), ("/pedidos/{rascunho}/sugestoes/produtos/?q=toner", True)]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/pedidos`.
- [ ] **Step 3: Implementar**
  - Tela igual a `identidade-visual-v3.html` (organização B): cartões "Cliente" e "Itens do pedido" e o "Resumo" fixo ao lado. No celular, uma coluna só, com a barra fixa embaixo mostrando o total e o botão "Confirmar". O selo diz "Rascunho · salvo às HH:MM".
  - Cada ação de mudança responde com `editor.html#atualizacao`: `#itens` é a troca principal, e `#resumo` e `#barra-celular` vão com `hx-swap-oob="true"`. As mensagens aparecem em `#msg-cliente`, `#msg-produto` e `#erro-desconto`, com `campo-invalido`. `avisos_do_rascunho` marca as linhas com problema e lista os avisos gerais no resumo.
  - Busca com `hx-get` e `hx-trigger="input changed delay:300ms, focus"`; enquanto carrega, a lista mostra três linhas de esqueleto (classe `htmx-request`). Até 6 resultados. Produto com estoque 0 → "Sem estoque"; disponível igual a 0 → "Todo no pedido"; nesses dois casos, a opção fica com `aria-disabled="true"` e sem `hx-post`. Disponível de 3 ou menos → selo âmbar "N disponíveis".
  - Botões − e + de cada linha (`acao=menos|mais`); remover com a animação de saída (`hx-swap="outerHTML swap:280ms"`). Observações gravadas com `hx-trigger="change, keyup changed delay:800ms"`.
  - Confirmar: se der certo, `redirecionar` para o detalhe com `messages.success("Pedido nº 1.042 confirmado")`. `ConfirmacaoRecusada` mostra os motivos no resumo (`role="alert"`); `PrecosAlterados` mostra "CE285A: de R$ 179,90 para R$ 189,90" e "Confira o novo total e confirme de novo." `PermissionDenied` vira 403 (o `app.js` mostra o aviso). O `editar` de um rascunho que a pessoa não pode editar, ou de um pedido que já não é rascunho, redireciona para o detalhe com o aviso explicando o motivo.
  - Animação do total: o `app.js` anima, ao trocar o conteúdo, os elementos `[data-valor-centavos]` a partir do valor anterior, em 520 ms (sem animação com "reduzir movimento").
  - O detalhe ganha "Continuar editando" (quando `pode_editar`) e "Repetir pedido" (confirmado ou cancelado). A lista ganha "+ Novo pedido" (formulário POST).
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`. Abrir um rascunho no navegador e comparar com o esboço, no computador e no celular.
- [ ] **Step 5: Commit.** `git commit -m "feat: tela de novo pedido com busca, resumo e confirmação"`

### Tarefa 20: PDF do pedido e fluxo completo no navegador

**Files:**
- Create: `apps/core/pdf.py`, `apps/core/pdf_recursos/Inter-Regular.ttf`, `apps/core/pdf_recursos/Inter-SemiBold.ttf`, `apps/core/pdf_recursos/OFL.txt`, `apps/core/pdf_recursos/logo-helptoner.png`, `apps/pedidos/pdf.py`, `tests/pedidos/test_pdf.py`, `tests/e2e/test_pedido.py`
- Modify: `apps/pedidos/views.py`, `apps/pedidos/urls.py`, `templates/pedidos/detalhe.html` (botão "PDF")
- Run: `uv add fpdf2` e `uv add --dev pypdf`

**Interfaces:**
- Produces:
  - `apps.core.pdf.DocumentoPDF(FPDF)`, com o construtor `(titulo: str, subtitulo: str = "", orientacao: Literal["P", "L"] = "P")`: página A4, fonte Inter (TTF de `pdf_recursos/`, que fica dentro do pacote Python para entrar no pacote da função na Vercel), cabeçalho com o logo e o título, e rodapé "Página X de Y · gerado em DD/MM/AAAA HH:MM" (hora de Brasília). Métodos: `tabela(colunas: list[tuple[str, float, str]], linhas: list[list[str]]) -> None`, em que cada coluna é `(rótulo, largura em mm, "L" | "R" | "C")` e o cabeçalho se repete quando a página quebra; e `para_bytes() -> bytes`.
  - `apps.pedidos.pdf.gerar_pdf_pedido(pedido: Pedido) -> bytes`.
  - Rota `pedidos:pdf` (`/pedidos/<id>/pdf/`, GET, todos).

- [ ] **Step 1: Escrever os testes que falham**

```python
def texto_do_pdf(dados: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(dados)).pages)

def test_pdf_tem_os_dados_e_aceita_acentos(vendedor):
    cli = criar_cliente("João & Cia — Comércio Ltda", documento="12ABC34501DE35", cidade="São José")
    ped = montar_pedido_confirmado(vendedor, cliente=cli, itens=[(com_estoque(criar_produto(preco="125.00"), 5, "60.00"), 2)],
                                   desconto=("percentual", "10"))
    dados = gerar_pdf_pedido(ped)
    texto = texto_do_pdf(dados)
    assert dados.startswith(b"%PDF-")
    for trecho in ["Pedido nº 1", "João & Cia — Comércio Ltda", "12.ABC.345/01DE-35", "São José",
                   "Toner HP 85A Preto", "R$ 250,00", "Desconto (10%)", "R$ 225,00", "Emitido por Carla"]:
        assert trecho in texto
    assert "Custo" not in texto and "Lucro" not in texto

def test_pdf_do_cancelado_vem_marcado(vendedor, administrador):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    ped = cancelar_pedido(ped.pk, "Cliente desistiu", administrador)
    texto = texto_do_pdf(gerar_pdf_pedido(ped))
    assert "CANCELADO" in texto and "Cliente desistiu" in texto

def test_download_e_rascunho_sem_pdf(client_vendedor, vendedor):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    r = client_vendedor.get(f"/pedidos/{ped.pk}/pdf/")
    assert r["Content-Type"] == "application/pdf" and 'filename="pedido-1.pdf"' in r["Content-Disposition"]
    rasc = criar_rascunho(vendedor)
    r = client_vendedor.get(f"/pedidos/{rasc.pk}/pdf/", follow=True)
    assert "O PDF fica disponível depois de confirmar o pedido." in r.content.decode()

def test_falha_ao_gerar_pdf_avisa(client_vendedor, vendedor, monkeypatch, caplog):
    ped = montar_pedido_confirmado(vendedor, itens=[(com_estoque(criar_produto(), 5), 1)])
    monkeypatch.setattr("apps.pedidos.views.gerar_pdf_pedido", Mock(side_effect=RuntimeError("falhou")))
    r = client_vendedor.get(f"/pedidos/{ped.pk}/pdf/", follow=True)
    assert "Não foi possível gerar o PDF. Tente de novo; se continuar, avise o administrador." in r.content.decode()
    assert any(rec.exc_info for rec in caplog.records)

# tests/e2e/test_pedido.py
def test_pedido_do_comeco_ao_fim(pagina, live_server, administrador):
    criar_cliente("Papelaria Central Ltda", documento="11222333000181")
    prod = com_estoque(criar_produto(preco="189.90"), 12, por=administrador)
    entrar(pagina, live_server, administrador)
    pagina.get_by_role("link", name="Pedidos").click()
    pagina.get_by_role("button", name="+ Novo pedido").click()
    pagina.get_by_placeholder("Buscar cliente por nome, CPF ou CNPJ").fill("papel")
    pagina.get_by_role("option", name=re.compile("Papelaria Central")).click()
    campo = pagina.get_by_placeholder("Buscar produto por código ou nome")
    campo.fill("ce285")
    expect(pagina.get_by_role("option", name=re.compile("CE285A"))).to_be_visible()
    campo.press("Enter")
    pagina.get_by_label("Quantidade").fill("2")
    pagina.get_by_label("Quantidade").press("Enter")
    expect(pagina.locator("#itens")).to_contain_text("Toner HP 85A Preto")
    pagina.get_by_label("Desconto", exact=True).fill("10")
    pagina.get_by_label("Desconto", exact=True).blur()
    expect(pagina.locator("#resumo")).to_contain_text("R$ 341,82")
    pagina.get_by_role("button", name="Confirmar pedido").click()
    expect(pagina.get_by_text("Pedido nº 1 confirmado")).to_be_visible()
    with pagina.expect_download() as baixado:
        pagina.get_by_role("link", name="PDF").click()
    assert Path(baixado.value.path()).read_bytes().startswith(b"%PDF-")
    pagina.get_by_role("button", name="Cancelar pedido").click()
    pagina.get_by_label("Motivo").fill("Cliente desistiu")
    pagina.get_by_role("dialog").get_by_role("button", name="Cancelar pedido").click()
    expect(pagina.get_by_text("Cancelado por Lucas")).to_be_visible()
    prod.refresh_from_db()
    assert prod.estoque == 12
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/pedidos/test_pdf.py && uv run pytest -m e2e`.
- [ ] **Step 3: Implementar**
  - Inter 4.1: `Inter-Regular.ttf` e `Inter-SemiBold.ttf` (TTF estáticos do arquivo da release) e o `OFL.txt` em `apps/core/pdf_recursos/`, junto com uma cópia do logo.
  - Conteúdo do PDF: logo; "Pedido nº 1.042"; data da confirmação e "Emitido por"; "CANCELADO" em vermelho, com data, quem cancelou e motivo, quando for o caso; cliente (nome, CPF ou CNPJ, telefone, e-mail e endereço completo); itens (Código, Descrição, Qtd., Unit., Total); subtotal, desconto e total; observações. Sem custo nem lucro.
  - View: rascunho → aviso e redireciona para o detalhe. Se der certo, responde com `Content-Disposition: attachment; filename="pedido-<numero>.pdf"`. Qualquer exceção na geração → `logger.exception(...)` (o Sentry recebe pela integração de logging), aviso de erro e redireciona para o detalhe.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` e `uv run pytest -m e2e`. Abrir um PDF e conferir o visual.
- [ ] **Step 5: Commit.** `git commit -m "feat: PDF do pedido e teste do fluxo completo no navegador"`

### Tarefa 21: Início

**Files:**
- Modify: `apps/core/views.py` (`inicio`), `templates/core/inicio.html` (partial `painel`), `apps/pedidos/consultas.py`, `tests/seguranca/test_sem_custo.py`
- Create: `tests/pedidos/test_inicio.py`

**Interfaces:**
- Consumes: `hoje`, `mes_de` e `intervalo_de_datas` (Tarefa 4).
- Produces (em `apps.pedidos.consultas`):
  - `NumerosDoMes(pedidos: int, vendido: Decimal, nome_do_mes: str)`.
  - `numeros_do_mes(usuario, agora: datetime | None = None) -> NumerosDoMes`: só pedidos confirmados (os cancelados não entram), no mês de Brasília; o Administrador vê a empresa, e o Vendedor vê os pedidos com `criado_por=usuario`.
  - `rascunhos_abertos(usuario, limite: int = 5) -> list[Pedido]`: os da própria pessoa, do mais recente para o mais antigo, anotados com `quantidade_itens`.
  - `ultimos_pedidos(limite: int = 5) -> list[Pedido]`: confirmados e cancelados, pela data de confirmação.

- [ ] **Step 1: Escrever os testes que falham**

```python
def confirmar_em(pedido, quando):
    Pedido.objects.filter(pk=pedido.pk).update(confirmado_em=quando)

def test_numeros_do_mes_no_fuso_de_brasilia(administrador):  # Review Focus 3
    prod = com_estoque(criar_produto(preco="100.00"), 10, por=administrador)
    a = montar_pedido_confirmado(administrador, itens=[(prod, 1)])
    b = montar_pedido_confirmado(administrador, itens=[(prod, 2)])
    confirmar_em(a, datetime(2026, 11, 1, 1, 30, tzinfo=UTC))  # 31/10 às 22h30 em Brasília
    confirmar_em(b, datetime(2026, 11, 1, 3, 30, tzinfo=UTC))  # 01/11 às 00h30 em Brasília
    n = numeros_do_mes(administrador, agora=datetime(2026, 11, 1, 2, 0, tzinfo=UTC))  # 31/10 às 23h
    assert n == NumerosDoMes(1, Decimal("100.00"), "outubro")

def test_vendedor_ve_so_os_proprios_numeros_e_cancelado_nao_conta(administrador, vendedor):
    prod = com_estoque(criar_produto(preco="100.00"), 10, por=administrador)
    montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    montar_pedido_confirmado(administrador, itens=[(prod, 1)])
    cancelado = montar_pedido_confirmado(vendedor, itens=[(prod, 1)])
    cancelar_pedido(cancelado.pk, "x", administrador)
    assert numeros_do_mes(vendedor).pedidos == 1 and numeros_do_mes(administrador).pedidos == 2

def test_rascunhos_sao_os_da_propria_pessoa(vendedor, administrador):
    meu = criar_rascunho(vendedor)
    criar_rascunho(administrador)
    assert rascunhos_abertos(vendedor) == [meu]

def test_tela_do_inicio(client_vendedor, vendedor):
    assert "Olá, Carla" in client_vendedor.get("/").content.decode()
    criar_rascunho(vendedor)
    html = client_vendedor.get("/", headers={"HX-Request": "true"}).content.decode()
    assert "Pedidos em" in html and "Vendido em" in html and "Continuar" in html

# tests/seguranca/test_sem_custo.py
PAGINAS += [("/", True)]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/pedidos/test_inicio.py`.
- [ ] **Step 3: Implementar** a tela como em `telas.html` (Início): "Olá, Carla" e o botão "+ Novo pedido"; o `#painel` carrega por HTMX, com esqueleto; dois números ("Pedidos em outubro" e "Vendido em outubro"); "Rascunhos em aberto" (cliente ou "Sem cliente", nº de itens, total e "Continuar"); "Últimos pedidos" (número, cliente, total e selo). Cada bloco vazio tem orientação ("Nenhum rascunho em aberto.").
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: Início com rascunhos, últimos pedidos e números do mês"`

---

## Etapa 6: Histórico

**Ao fim da etapa:** o Administrador vê quem mudou o quê e quando, além dos logins com e sem sucesso.

### Tarefa 22: Histórico de alterações e de acessos

**Files:**
- Create: `apps/core/historico.py`, `templates/core/historico.html` (partial `resultados`), `tests/core/test_historico.py`
- Modify: `apps/core/views.py`, `apps/core/urls.py`, `tests/seguranca/test_permissoes.py`

**Interfaces:**
- Consumes: os históricos de `Cliente`, `Produto` e `Usuario` (simple-history), `RegistroAcesso`, `navegador_legivel`, `brl` e `intervalo_de_datas`.
- Produces:
  - `Evento(quando: datetime, quem: str, tipo: str, descricao: str, sucesso: bool | None)`, em que `tipo` é "cliente", "produto", "funcionario" ou "login".
  - `descrever_alteracao(registro) -> str | None`: devolve `None` quando não há diferença visível nem motivo (por exemplo, o `last_login`).
  - `eventos(*, tipo: str = "", inicio: date, fim: date) -> list[Evento]`, do mais recente para o mais antigo, juntando as quatro fontes em Python.
  - Rota `core:historico` (`/historico/?tipo=&inicio=&fim=&pagina=`), só para o Administrador; o padrão é dos últimos 30 dias, com 50 por página.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_mudanca_de_preco_com_antes_e_depois(client_admin):
    p = criar_produto(preco="179.90")
    client_admin.post(f"/produtos/{p.pk}/", {"codigo": "CE285A", "descricao": p.descricao, "marca": "HP", "preco": "189,90"})
    e = eventos(inicio=hoje(), fim=hoje())[0]
    assert (e.tipo, e.quem, e.descricao) == ("produto", "Lucas Tonnon", "Produto CE285A: preço R$ 179,90 → R$ 189,90")

def test_cadastro_e_inativacao(client_vendedor):
    client_vendedor.post("/clientes/novo/", {"tipo": "PJ", "nome": "Papelaria Central Ltda", "documento": "11.222.333/0001-81"})
    client_vendedor.post(f"/clientes/{Cliente.objects.get().pk}/inativar/")
    assert [e.descricao for e in eventos(tipo="cliente", inicio=hoje(), fim=hoje())] == [
        "Cliente Papelaria Central Ltda inativado", "Cliente Papelaria Central Ltda cadastrado"]

def test_acoes_sobre_funcionarios(administrador, vendedor):
    redefinir_senha(vendedor, por=administrador)
    e = eventos(tipo="funcionario", inicio=hoje(), fim=hoje())[0]
    assert (e.quem, e.descricao) == ("Lucas Tonnon", "Funcionário Carla Souza: senha redefinida")

def test_logins(client, db):
    criar_usuario(email="carla@helptoner.com.br")
    client.post("/contas/login/", {"login": "carla@helptoner.com.br", "password": "senha-errada-de-novo"})
    e = eventos(tipo="login", inicio=hoje(), fim=hoje())[0]
    assert e.sucesso is False and e.descricao == "Login recusado · carla@helptoner.com.br (E-mail ou senha incorretos)"

def test_registro_sem_diferenca_nao_aparece(vendedor):
    antes = len(eventos(tipo="funcionario", inicio=hoje(), fim=hoje()))
    vendedor.last_login = timezone.now()
    vendedor.save(update_fields=["last_login"])
    assert len(eventos(tipo="funcionario", inicio=hoje(), fim=hoje())) == antes

def test_tela_filtra_por_tipo(client_admin):
    criar_produto()
    html = client_admin.get("/historico/?tipo=cliente", headers={"HX-Request": "true"}).content.decode()
    assert "Produto CE285A" not in html

# tests/seguranca/test_permissoes.py
ROTAS_SO_ADMIN += [("get", "/historico/")]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/core/test_historico.py`.
- [ ] **Step 3: Implementar**
  - Criação: "Cliente X cadastrado", "Produto X cadastrado", "Funcionário X criado".
  - Alteração: junta as diferenças de `diff_against` com os `verbose_name` dos campos. Valores em dinheiro com `brl`; o campo `ativo` vira "inativado" ou "reativado"; o `history_change_reason`, quando existe, é usado no lugar das diferenças, em minúsculas depois dos dois-pontos ("Funcionário Carla Souza: senha redefinida").
  - Logins: sucesso → "Login · Chrome no Windows"; falha → "Login recusado · e-mail (motivo)".
  - Tela como em `telas.html`: colunas Quando, Quem e O quê; selos "Login" e "Login recusado"; filtros de tipo (Tudo, Clientes, Produtos, Funcionários, Logins) e de período.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest`.
- [ ] **Step 5: Commit.** `git commit -m "feat: histórico de alterações e de acessos"`

---

## Etapa 7: Relatórios

**Ao fim da etapa:** o Administrador vê as sete abas de §7, com filtros, comparação com o período anterior, gráficos com versão em tabela e exportação para Excel e PDF, e os números batem com um conjunto conhecido de pedidos.

### Tarefa 23: Períodos e filtros

**Files:**
- Create: `apps/relatorios/__init__.py`, `apps/relatorios/apps.py`, `apps/relatorios/periodos.py`, `tests/relatorios/test_periodos.py`
- Modify: `config/settings/base.py` (`apps.relatorios`)

**Interfaces:**
- Produces (em `apps.relatorios.periodos`):
  - `Atalho(StrEnum)`: `TRES_MESES = "3m"`, `ANO = "ano"`, `DOZE_MESES = "12m"`, `DATAS = "datas"`.
  - `Agrupamento(StrEnum)`: `DIA = "dia"`, `SEMANA = "semana"`, `MES = "mes"`.
  - `Filtros(inicio: date, fim: date, agrupamento: Agrupamento, funcionario_id: int | None, atalho: Atalho)` (dataclass congelada), com o método `como_querystring() -> str`.
  - `deslocar_meses(dia: date, meses: int) -> date`: se o dia não existir no mês de destino, usa o último dia desse mês.
  - `periodo_do_atalho(atalho: Atalho, hoje: date) -> tuple[date, date]` e `periodo_anterior(f: Filtros) -> Filtros`, conforme P16.
  - `descricao_comparacao(f: Filtros) -> str`: "vs 3 meses anteriores", "vs 12 meses anteriores", "vs mesmo período de 2025" ou "vs N dias anteriores".
  - `ler_filtros(dados: Mapping[str, str], hoje: date) -> tuple[Filtros, list[str]]`. Sem nada informado: últimos 12 meses, agrupado por mês, todos os funcionários. Os erros vêm em português; quando há erro, os filtros com erro voltam ao padrão.

- [ ] **Step 1: Escrever os testes que falham**

```python
HOJE = date(2026, 10, 3)

def test_atalhos():
    assert periodo_do_atalho(Atalho.TRES_MESES, HOJE) == (date(2026, 8, 1), HOJE)
    assert periodo_do_atalho(Atalho.DOZE_MESES, HOJE) == (date(2025, 11, 1), HOJE)
    assert periodo_do_atalho(Atalho.ANO, HOJE) == (date(2026, 1, 1), HOJE)

@pytest.mark.parametrize("atalho,inicio,fim,anterior", [
    (Atalho.TRES_MESES, date(2026, 8, 1), HOJE, (date(2026, 5, 1), date(2026, 7, 3))),
    (Atalho.DOZE_MESES, date(2025, 11, 1), HOJE, (date(2024, 11, 1), date(2025, 10, 3))),
    (Atalho.ANO, date(2026, 1, 1), HOJE, (date(2025, 1, 1), date(2025, 10, 3))),
    (Atalho.DATAS, date(2026, 10, 1), HOJE, (date(2026, 9, 28), date(2026, 9, 30))),
])
def test_periodo_anterior(atalho, inicio, fim, anterior):
    f = Filtros(inicio, fim, Agrupamento.MES, None, atalho)
    p = periodo_anterior(f)
    assert (p.inicio, p.fim) == anterior

def test_deslocar_meses_no_fim_do_mes():
    assert deslocar_meses(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert deslocar_meses(date(2024, 2, 29), -12) == date(2023, 2, 28)

def test_padrao_e_erros():
    f, erros = ler_filtros({}, HOJE)
    assert (f.atalho, f.inicio, f.fim, f.agrupamento, f.funcionario_id, erros) == (
        Atalho.DOZE_MESES, date(2025, 11, 1), HOJE, Agrupamento.MES, None, [])
    _, erros = ler_filtros({"atalho": "datas", "inicio": "2026-10-05", "fim": "2026-10-01"}, HOJE)
    assert erros == ["A data inicial precisa ser antes da final."]
    _, erros = ler_filtros({"atalho": "12m", "agrupamento": "dia"}, HOJE)
    assert erros == ["Para agrupar por dia, escolha um período de até 366 dias."]
    _, erros = ler_filtros({"funcionario": "abc"}, HOJE)
    assert erros == ["Funcionário inválido."]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/relatorios/test_periodos.py`.
- [ ] **Step 3: Implementar** as funções da seção Interfaces.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest tests/relatorios`.
- [ ] **Step 5: Commit.** `git commit -m "feat: períodos e filtros dos relatórios"`

### Tarefa 24: Consultas do Resumo e de Vendas por período

**Files:**
- Create: `apps/relatorios/tabelas.py`, `apps/relatorios/consultas.py`, `tests/relatorios/conftest.py`, `tests/relatorios/test_resumo.py`, `tests/relatorios/test_vendas.py`

**Interfaces:**
- Consumes: `Filtros` e `periodo_anterior` (Tarefa 23), `intervalo_de_datas` e `FUSO` (Tarefa 4) e `margem` (Tarefa 14).
- Produces:
  - Em `apps.relatorios.tabelas`: `Coluna(rotulo: str, tipo: Literal["texto", "dinheiro", "inteiro", "percentual", "data"])` e `Tabela(titulo: str, colunas: list[Coluna], linhas: list[list[object]])`.
  - Em `apps.relatorios.consultas`:
    - `itens_confirmados(f: Filtros) -> QuerySet[ItemPedido]`: itens de pedidos **confirmados** (os cancelados ficam de fora) com `confirmado_em` no intervalo de Brasília e, se houver, `criado_por=f.funcionario_id`. Anota `receita = quantidade × preço − desconto_rateado` e `custo = quantidade × custo_unitario`, com `ExpressionWrapper` decimal.
    - `Indicadores(faturamento: Decimal, lucro: Decimal, margem: Decimal | None, pedidos: int, ticket_medio: Decimal | None)`.
    - `Comparacao(atual: Indicadores, anterior: Indicadores, descricao: str)`, com `variacao(campo: str) -> Decimal | int | None`: faturamento, lucro e ticket médio em fração (4 casas; `None` se o anterior for 0); margem em diferença de frações; pedidos em diferença absoluta.
    - `indicadores(f: Filtros) -> Indicadores` e `comparar(f: Filtros) -> Comparacao`.
    - `serie(f: Filtros) -> list[dict]`: uma linha por dia, semana (começando na segunda) ou mês de Brasília, inclusive os períodos sem venda (zerados). Chaves: `periodo` (date), `rotulo` ("out/26", "28/09" ou "02/10"), `pedidos`, `bruto`, `descontos`, `liquido`, `lucro`, `margem` e `ticket`.
    - `top_produtos(f: Filtros, limite: int = 6) -> list[dict]`, com as chaves `codigo`, `descricao`, `quantidade`, `faturamento`, `lucro` e `margem`.
    - `clientes_sem_comprar(dias: int, hoje: date, funcionario_id: int | None = None) -> list[dict]`: clientes cujo último pedido confirmado (data de Brasília) tem **mais** de `dias` dias. Chaves: `cliente_id`, `nome`, `ultimo_pedido` (date), `ultimo_pedido_id`, `dias` e `produtos` (até 3 códigos do último pedido).
  - Fixture `cenario` (em `tests/relatorios/conftest.py`), montada com os serviços reais e com as datas ajustadas por `update` depois. Devolve um `SimpleNamespace` com `lucas` e `carla` (as fixtures `administrador` e `vendedor`), `c1`, `c2`, `ce285a`, `tn1060`, `cf217a` e `pedido1` a `pedido4` e `rascunho`:

| Pedido | Emitido por | Cliente | Itens | Desconto | Total | Lucro | Confirmado em (Brasília) |
|---|---|---|---|---|---|---|---|
| nº 1 | Carla | C1 Papelaria Central Ltda | 2 × CE285A + 1 × TN-1060 | 10% | 225,00 | 85,00 | 15/09/2026 10:00 |
| nº 2 | Lucas | C2 Clínica Bem Viver | 1 × CE285A | — | 100,00 | 40,00 | 30/09/2026 22:30 (01/10 01:30 UTC) |
| nº 3 | Carla | C1 | 3 × TN-1060 | R$ 15 | 135,00 | 75,00 | 02/10/2026 09:00 |
| nº 4 | Lucas | C2 | 1 × TN-1060 | — | 50,00 | — | 02/10/2026 11:00; cancelado por Lucas em 03/10/2026 10:00, motivo "Cliente desistiu" |
| rascunho | Carla | C1 | 1 × CE285A | — | — | — | — |

  Produtos: CE285A "Toner HP 85A Preto" (HP, preço 100,00, estoque inicial 100 a 60,00); TN-1060 "Toner Brother TN-1060" (Brother, preço 50,00, estoque inicial 100 a 20,00); CF217A "Toner HP 17A Preto" (HP, preço 80,00, sem estoque).

- [ ] **Step 1: Escrever os testes que falham**

```python
def F(inicio, fim, agrupamento=Agrupamento.MES, funcionario_id=None):
    return Filtros(inicio, fim, agrupamento, funcionario_id, Atalho.DATAS)

SET = F(date(2026, 9, 1), date(2026, 9, 30))

def test_indicadores_de_setembro(cenario):
    assert indicadores(SET) == Indicadores(Decimal("325.00"), Decimal("125.00"), Decimal("0.3846"), 2, Decimal("162.50"))

def test_filtro_de_funcionario(cenario):
    assert indicadores(F(date(2026, 9, 1), date(2026, 9, 30), funcionario_id=cenario.carla.pk)) == Indicadores(
        Decimal("225.00"), Decimal("85.00"), Decimal("0.3778"), 1, Decimal("225.00"))

def test_borda_do_fuso_cancelado_e_rascunho(cenario):  # Review Focus 3
    assert indicadores(F(date(2026, 10, 1), date(2026, 10, 3))) == Indicadores(
        Decimal("135.00"), Decimal("75.00"), Decimal("0.5556"), 1, Decimal("135.00"))

def test_comparacao_com_o_periodo_anterior(cenario):
    c = comparar(F(date(2026, 10, 1), date(2026, 10, 3)))  # anterior: 28 a 30/09, só o nº 2
    assert c.anterior.faturamento == Decimal("100.00") and c.descricao == "vs 3 dias anteriores"
    assert (c.variacao("faturamento"), c.variacao("lucro"), c.variacao("margem"), c.variacao("pedidos")) == (
        Decimal("0.3500"), Decimal("0.8750"), Decimal("0.1556"), 0)
    assert comparar(SET).variacao("faturamento") is None  # agosto sem vendas

def test_serie_mensal(cenario):
    s = serie(F(date(2026, 9, 1), date(2026, 10, 31)))
    assert [(x["rotulo"], x["pedidos"], x["bruto"], x["descontos"], x["liquido"], x["lucro"]) for x in s] == [
        ("set/26", 2, Decimal("350.00"), Decimal("25.00"), Decimal("325.00"), Decimal("125.00")),
        ("out/26", 1, Decimal("150.00"), Decimal("15.00"), Decimal("135.00"), Decimal("75.00"))]

def test_serie_diaria_com_dias_zerados(cenario):
    s = serie(F(date(2026, 9, 29), date(2026, 10, 1), Agrupamento.DIA))
    assert [(x["rotulo"], x["liquido"]) for x in s] == [("29/09", Decimal("0.00")), ("30/09", Decimal("100.00")),
                                                         ("01/10", Decimal("0.00"))]

def test_top_produtos(cenario):
    assert [(p["codigo"], p["quantidade"], p["faturamento"], p["lucro"]) for p in top_produtos(F(date(2026, 9, 1), date(2026, 10, 31)))] == [
        ("CE285A", 3, Decimal("280.00"), Decimal("100.00")), ("TN-1060", 4, Decimal("180.00"), Decimal("100.00"))]

def test_clientes_sem_comprar(cenario):  # C1: 60 dias (fica de fora); C2: 62 dias
    r = clientes_sem_comprar(60, date(2026, 12, 1))
    assert [(x["nome"], x["ultimo_pedido"], x["dias"], x["produtos"], x["ultimo_pedido_id"]) for x in r] == [
        ("Clínica Bem Viver", date(2026, 9, 30), 62, ["CE285A"], cenario.pedido2.pk)]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/relatorios`.
- [ ] **Step 3: Implementar.** Agregações em SQL (`Sum`, `Count("pedido", distinct=True)`); agrupamento com `TruncDay`, `TruncWeek` ou `TruncMonth` em `pedido__confirmado_em`, com `tzinfo=FUSO`; preenchimento dos períodos vazios em Python; arredondamento final com `arredondar` e a margem com `margem()`.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest tests/relatorios`.
- [ ] **Step 5: Commit.** `git commit -m "feat: consultas de indicadores, série temporal e clientes sem comprar"`

### Tarefa 25: Consultas das demais abas

**Files:**
- Modify: `apps/relatorios/consultas.py`
- Create: `tests/relatorios/test_abas.py`

**Interfaces:**
- Consumes: `itens_confirmados`, `Tabela` e o `cenario` (Tarefa 24).
- Produces (em `apps.relatorios.consultas`):
  - `ranking_clientes(f) -> list[dict]`: `cliente_id`, `nome`, `valor`, `pedidos`, `lucro` e `ultimo_pedido` (data de Brasília do último pedido confirmado, em qualquer período). Ordenado por valor, do maior para o menor.
  - `produtos(f) -> list[dict]` e `marcas(f) -> list[dict]`: `codigo`, `descricao`, `marca` (ou só `marca`), `quantidade`, `faturamento`, `lucro`, `margem` e `participacao` (fração do faturamento total, com 4 casas).
  - `funcionarios(f) -> list[dict]`: `usuario_id`, `nome`, `pedidos`, `valor`, `lucro` e `desconto_medio` (Σ desconto ÷ Σ subtotal, com 4 casas).
  - `estoque(f) -> dict`: `{"produtos": [...], "zerados": [...], "movimentos": {...}, "valor_total": Decimal}`. Em `produtos`, cada linha tem `codigo`, `descricao`, `estoque`, `custo_medio` e `valor_em_estoque`, só dos produtos ativos. `zerados` são os códigos dos ativos com estoque 0. `movimentos` tem as somas de quantidade no período (`entradas`, que inclui o estoque inicial, `saidas`, `devolucoes`, `ajustes_mais` e `ajustes_menos`); o filtro de funcionário vale para quem lançou.
  - `cancelamentos(f) -> list[dict]`: `pedido_id`, `numero`, `cliente`, `valor`, `motivo`, `cancelado_por`, `cancelado_em` e `emitido_por`. O período é o da data do cancelamento.
  - `ABAS = {"resumo": "Resumo", "vendas": "Vendas por período", "clientes": "Clientes", "produtos": "Produtos e marcas", "funcionarios": "Funcionários", "estoque": "Estoque", "cancelamentos": "Cancelamentos"}`.
  - `Relatorio(aba: str, titulo: str, tabelas: list[Tabela], comparacao: Comparacao | None = None, graficos: dict | None = None)`.
  - `montar_aba(aba: str, f: Filtros, hoje: date, dias_sem_comprar: int = 60) -> Relatorio`: monta as `Tabela` que a tela e as exportações usam, e os dados dos gráficos (só no Resumo).

- [ ] **Step 1: Escrever os testes que falham**

```python
TUDO = F(date(2026, 9, 1), date(2026, 10, 31))

def test_produtos_e_marcas(cenario):
    assert [(p["codigo"], p["quantidade"], p["faturamento"], p["lucro"], p["margem"], p["participacao"]) for p in produtos(TUDO)] == [
        ("CE285A", 3, Decimal("280.00"), Decimal("100.00"), Decimal("0.3571"), Decimal("0.6087")),
        ("TN-1060", 4, Decimal("180.00"), Decimal("100.00"), Decimal("0.5556"), Decimal("0.3913"))]
    assert [(m["marca"], m["faturamento"]) for m in marcas(TUDO)] == [("HP", Decimal("280.00")), ("Brother", Decimal("180.00"))]

def test_funcionarios(cenario):
    assert [(x["nome"], x["pedidos"], x["valor"], x["lucro"], x["desconto_medio"]) for x in funcionarios(TUDO)] == [
        ("Carla Souza", 2, Decimal("360.00"), Decimal("160.00"), Decimal("0.1000")),
        ("Lucas Tonnon", 1, Decimal("100.00"), Decimal("40.00"), Decimal("0.0000"))]

def test_ranking_de_clientes(cenario):
    assert [(x["nome"], x["valor"], x["pedidos"], x["lucro"], x["ultimo_pedido"]) for x in ranking_clientes(TUDO)] == [
        ("Papelaria Central Ltda", Decimal("360.00"), 2, Decimal("160.00"), date(2026, 10, 2)),
        ("Clínica Bem Viver", Decimal("100.00"), 1, Decimal("40.00"), date(2026, 9, 30))]

def test_cancelamentos_pela_data_do_cancelamento(cenario):
    assert [(x["numero"], x["valor"], x["motivo"], x["cancelado_por"]) for x in cancelamentos(F(date(2026, 10, 1), date(2026, 10, 31)))] == [
        (4, Decimal("50.00"), "Cliente desistiu", "Lucas Tonnon")]
    assert cancelamentos(F(date(2026, 10, 1), date(2026, 10, 2))) == []

def test_estoque(cenario):
    dia = hoje()
    e = estoque(F(dia - timedelta(days=1), dia + timedelta(days=1)))
    assert [(p["codigo"], p["estoque"], p["custo_medio"], p["valor_em_estoque"]) for p in e["produtos"]] == [
        ("CE285A", 97, Decimal("60.0000"), Decimal("5820.00")), ("CF217A", 0, Decimal("0.0000"), Decimal("0.00")),
        ("TN-1060", 96, Decimal("20.0000"), Decimal("1920.00"))]
    assert e["zerados"] == ["CF217A"] and e["valor_total"] == Decimal("7740.00")
    assert e["movimentos"] == {"entradas": 200, "saidas": 8, "devolucoes": 1, "ajustes_mais": 0, "ajustes_menos": 0}

@pytest.mark.parametrize("aba", list(ABAS))
def test_montar_aba(cenario, aba):
    rel = montar_aba(aba, TUDO, date(2026, 12, 1))
    assert rel.titulo == ABAS[aba] and rel.tabelas and all(len(l) == len(t.colunas) for t in rel.tabelas for l in t.linhas)
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/relatorios/test_abas.py`.
- [ ] **Step 3: Implementar.** Tabelas de cada aba, seguindo §7: Resumo (indicadores, série, top produtos e clientes sem comprar há mais de 60 dias); Vendas (Período, Pedidos, Bruto, Descontos, Líquido, Lucro, Margem e Valor médio); Clientes (ranking + sem comprar há `dias_sem_comprar` dias); Produtos e marcas (duas tabelas); Funcionários; Estoque (produtos, zerados e movimentos); Cancelamentos.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest tests/relatorios`.
- [ ] **Step 5: Commit.** `git commit -m "feat: consultas das abas de clientes, produtos, funcionários, estoque e cancelamentos"`

### Tarefa 26: Telas dos relatórios e gráficos

**Files:**
- Create: `apps/relatorios/views.py`, `apps/relatorios/urls.py`, `templates/relatorios/pagina.html` (partial `conteudo`), `templates/relatorios/_resumo.html`, `templates/componentes/tabela.html`, `static/js/graficos.js`, `tests/relatorios/test_telas.py`
- Modify: `config/urls.py`, `tests/seguranca/test_permissoes.py`

**Interfaces:**
- Consumes: `ler_filtros` (Tarefa 23), `montar_aba` e `ABAS` (Tarefa 25) e `repetir_pedido` pela rota `pedidos:repetir` (Tarefa 19).
- Produces:
  - Rotas `relatorios:resumo` (`/relatorios/`) e `relatorios:aba` (`/relatorios/<aba>/`), só para o Administrador; aba desconhecida dá 404.
  - `componentes/tabela.html`: desenha uma `Tabela`, formatando cada célula pelo tipo da coluna (`brl`, `inteiro`, `pct`, `data_br` ou texto), com `tabela-responsiva`.
  - O JSON dos gráficos sai com `json_script`, nos ids `dados-grafico-linha` (`{"rotulos": [...], "series": [{"nome", "cor", "valores": [str], "textos": [str]}]}`) e `dados-grafico-barras` (`{"itens": [{"codigo", "descricao", "valor", "texto", "detalhes": [str]}]}`). Os valores vão como texto decimal e os rótulos já formatados pelo servidor.

- [ ] **Step 1: Escrever os testes que falham**

```python
URL_SET = "?atalho=datas&inicio=2026-09-01&fim=2026-09-30"

def test_resumo_com_indicadores_e_comparacao(client_admin, cenario):
    html = client_admin.get("/relatorios/" + URL_SET, headers={"HX-Request": "true"}).content.decode()
    for trecho in ["R$ 325,00", "R$ 125,00", "38,5%", "R$ 162,50", "vs 30 dias anteriores"]:
        assert trecho in html
    assert 'id="dados-grafico-linha" type="application/json"' in html
    assert "Faturamento líquido" in html and "<table" in html  # toda visualização tem a versão em tabela

@pytest.mark.parametrize("aba", ["vendas", "clientes", "produtos", "funcionarios", "estoque", "cancelamentos"])
def test_cada_aba_abre(client_admin, cenario, aba):
    r = client_admin.get(f"/relatorios/{aba}/{URL_SET}", headers={"HX-Request": "true"})
    assert r.status_code == 200 and ABAS[aba] in r.content.decode()

def test_filtro_invalido_mostra_aviso(client_admin):
    r = client_admin.get("/relatorios/?atalho=datas&inicio=2026-10-05&fim=2026-10-01", headers={"HX-Request": "true"})
    assert "A data inicial precisa ser antes da final." in r.content.decode()

def test_aba_desconhecida(client_admin):
    assert client_admin.get("/relatorios/nada/").status_code == 404

# tests/seguranca/test_permissoes.py
ROTAS_SO_ADMIN += [("get", "/relatorios/")] + [("get", f"/relatorios/{a}/") for a in
                   ["vendas", "clientes", "produtos", "funcionarios", "estoque", "cancelamentos"]]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/relatorios/test_telas.py`.
- [ ] **Step 3: Implementar**
  - Página como em `relatorios.html`. Abas são links que mantêm a query. A barra de filtros é um formulário GET com `hx-get` para a mesma URL, `hx-target="#conteudo"`, `hx-push-url="true"` e `hx-indicator="#conteudo"`; ao trocar o filtro, o conteúdo fica no lugar, apagado (`#conteudo.htmx-request` com opacidade de 0,55 e transição), sem esqueleto. Só a primeira carga usa esqueleto. A barra tem os botões "⤓ Excel" e "⤓ PDF", que são links com a query (a rota chega na Tarefa 27).
  - Resumo: blocos de indicadores com a variação ("▲ subiu 35% vs …" ou "▼ caiu …"; margem em "p.p."; pedidos em número); o gráfico de linhas com a chave "Gráfico | Tabela" (a tabela vem do servidor e o JS só alterna o atributo `hidden`); as barras dos produtos que mais faturaram; os clientes sem comprar há mais de 60 dias, com o botão "Repetir pedido" (formulário POST para `pedidos:repetir`).
  - `graficos.js`: adaptar `grafico()` e `barras()` de `docs/esbocos/relatorios.html`. Os dados vêm de `JSON.parse(document.getElementById(id).textContent)`; nada de `innerHTML` nem de atributo `style` (usar elementos, classes e `textContent`; para posicionar a caixa de valores, usar `elemento.style.left = ...`, que a CSP permite). Mantém as regras de §7: cores `#0200FF` e `#eb6834`, uma escala por gráfico, linhas de 2 px, barras de até 24 px com ponta arredondada, rótulos diretos só nos pontos finais e mira vertical com caixa de valores pelo mouse e pelas setas do teclado. Redesenha quando a janela muda de tamanho (com espera) e depois de `htmx:afterSwap` em `#conteudo`.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` e `uv run pytest tests/seguranca/test_csp_nos_arquivos.py`. Abrir no navegador e comparar com `relatorios.html` (mouse e teclado).
- [ ] **Step 5: Commit.** `git commit -m "feat: telas dos relatórios com filtros, comparação e gráficos"`

### Tarefa 27: Exportação para Excel e PDF

**Files:**
- Create: `apps/relatorios/exportacao.py`, `tests/relatorios/test_exportacao.py`, `tests/e2e/test_relatorios.py`
- Modify: `apps/relatorios/views.py`, `apps/relatorios/urls.py`, `tests/seguranca/test_permissoes.py`
- Run: `uv add openpyxl`

**Interfaces:**
- Consumes: `Relatorio`, `Tabela` e `montar_aba` (Tarefa 25) e `DocumentoPDF` (Tarefa 20).
- Produces:
  - `para_excel(rel: Relatorio, f: Filtros) -> bytes`: uma planilha por `Tabela` (nome com até 31 caracteres). A linha 1 tem o título e os filtros; o cabeçalho vai em negrito. Formatos: dinheiro `'"R$" #,##0.00'`, percentual `'0.0%'`, data `'dd/mm/yyyy'`. Textos sempre gravados como texto (`celula.data_type = "s"`), para nome de cliente começando com "=" nunca virar fórmula.
  - `para_pdf(rel: Relatorio, f: Filtros) -> bytes`: `DocumentoPDF(..., orientacao="L")`, com o título, os filtros e cada tabela.
  - Rota `relatorios:exportar` (`/relatorios/<aba>/<formato>/`, com `formato` em `excel` ou `pdf`), só para o Administrador. Arquivo `relatorio-<aba>-<inicio>-a-<fim>.xlsx` ou `.pdf`.

- [ ] **Step 1: Escrever os testes que falham**

```python
SET = F(date(2026, 9, 1), date(2026, 9, 30))

def test_excel_com_numeros_de_verdade(cenario):
    ws = load_workbook(BytesIO(para_excel(montar_aba("vendas", SET, date(2026, 12, 1)), SET))).active
    linha = next(r for r in ws.iter_rows() if r[0].value == "set/26")
    liquido = linha[4]
    assert liquido.data_type == "n" and Decimal(str(liquido.value)) == Decimal("325.00") and "R$" in liquido.number_format

def test_excel_nunca_cria_formula_com_dado_de_cadastro(cenario, administrador):
    cli = criar_cliente('=HYPERLINK("http://x","clique")')
    montar_pedido_confirmado(administrador, cliente=cli, itens=[(cenario.ce285a, 1)])
    dia = hoje()
    wb = load_workbook(BytesIO(para_excel(montar_aba("clientes", F(dia, dia), dia), F(dia, dia))))
    celulas = [c for ws in wb for r in ws.iter_rows() for c in r if isinstance(c.value, str) and c.value.startswith("=HYPERLINK")]
    assert celulas and all(c.data_type == "s" for c in celulas)

def test_pdf_valido(cenario):
    dados = para_pdf(montar_aba("vendas", SET, date(2026, 12, 1)), SET)
    texto = texto_do_pdf(dados)
    assert dados.startswith(b"%PDF-") and "Vendas por período" in texto and "R$ 325,00" in texto

def test_download_respeita_os_filtros(client_admin, cenario):
    r = client_admin.get("/relatorios/vendas/excel/?atalho=datas&inicio=2026-09-01&fim=2026-09-30")
    assert 'filename="relatorio-vendas-2026-09-01-a-2026-09-30.xlsx"' in r["Content-Disposition"]
    assert r["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

def test_falha_na_exportacao_avisa(client_admin, cenario, monkeypatch):
    monkeypatch.setattr("apps.relatorios.views.para_pdf", Mock(side_effect=RuntimeError))
    r = client_admin.get("/relatorios/vendas/pdf/?atalho=12m", follow=True)
    assert "Não foi possível gerar o arquivo. Tente de novo; se continuar, avise o administrador." in r.content.decode()

# tests/seguranca/test_permissoes.py
ROTAS_SO_ADMIN += [("get", "/relatorios/vendas/excel/"), ("get", "/relatorios/vendas/pdf/")]

# tests/e2e/test_relatorios.py
def test_exportar_relatorio(pagina, live_server, administrador):
    entrar(pagina, live_server, administrador)
    pagina.get_by_role("link", name="Relatórios").click()
    pagina.get_by_role("link", name="Vendas por período").click()
    with pagina.expect_download() as excel:
        pagina.get_by_role("link", name="⤓ Excel").click()
    load_workbook(excel.value.path())
    with pagina.expect_download() as pdf:
        pagina.get_by_role("link", name="⤓ PDF").click()
    assert Path(pdf.value.path()).read_bytes().startswith(b"%PDF-")
```

(`texto_do_pdf` vai para `tests/apoio.py`, para ser usado aqui e na Tarefa 20.)

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/relatorios/test_exportacao.py`.
- [ ] **Step 3: Implementar** as funções da seção Interfaces. A view trata qualquer exceção como na Tarefa 20 (log, aviso e redirecionamento para a aba com os mesmos filtros).
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` e `uv run pytest -m e2e`.
- [ ] **Step 5: Commit.** `git commit -m "feat: exportação dos relatórios para Excel e PDF"`

---

## Etapa 8: Publicação e operação

**Ao fim da etapa:** o sistema está no ar na Vercel (gru1) com o banco no Neon (São Paulo). Cada envio passa pelo CI; publicar é um botão com backup antes; há backup toda noite, teste de restauração todo mês e monitoramento; o guia de operação explica tudo.

### Tarefa 28: Configuração de produção (Vercel, Neon e Sentry)

**Files:**
- Create: `vercel.json`, `.vercelignore`, `scripts/__init__.py`, `scripts/vercel_build.py`, `apps/core/sentry.py`, `tests/seguranca/test_producao.py`
- Modify: `config/settings/producao.py`, `apps/core/views.py` (`erro_500`), `pyproject.toml`, `.env.exemplo`
- Run: `uv add "sentry-sdk[django]"`

**Interfaces:**
- Produces:
  - `apps.core.sentry.limpar_evento(evento: dict, dica: dict) -> dict`: apaga `user`, `request.cookies`, `request.headers`, `request.data`, `request.query_string` e `request.env`, e deixa em `request.url` só o caminho, sem a query.
  - `scripts/vercel_build.py`, com a função `main(env: Mapping[str, str], rodar=subprocess.run) -> None` (o teste importa `from scripts.vercel_build import main`; o bloco `if __name__ == "__main__"` chama `main(os.environ)`).

- [ ] **Step 1: Escrever os testes que falham**

```python
ENV_VERCEL = {"DJANGO_SETTINGS_MODULE": "config.settings.producao", "DJANGO_SECRET_KEY": "x" * 60,
              "DATABASE_URL": "postgres://u:p@ep-x-pooler.sa-east-1.aws.neon.tech/db?sslmode=require",
              "VERCEL_URL": "helptoner-abc.vercel.app", "VERCEL_PROJECT_PRODUCTION_URL": "helptoner.vercel.app",
              "DJANGO_ALLOWED_HOSTS": "pedidos.helptoner.com.br", "SENTRY_DSN": "https://abc@o0.ingest.sentry.io/0"}
SCRIPT = ("import json, django; django.setup(); from django.conf import settings as s; import sentry_sdk; "
          "o = sentry_sdk.get_client().options; d = s.DATABASES['default']; "
          "print(json.dumps({'hosts': s.ALLOWED_HOSTS, 'csrf': s.CSRF_TRUSTED_ORIGINS, 'idade': d['CONN_MAX_AGE'], "
          "'cursores': d['DISABLE_SERVER_SIDE_CURSORS'], 'ssl': d['OPTIONS'].get('sslmode'), "
          "'prepare': d['OPTIONS'].get('prepare_threshold', 'ausente'), 'ip': s.ALLAUTH_TRUSTED_CLIENT_IP_HEADER, "
          "'pii': o['send_default_pii'], 'corpo': o['max_request_body_size'], 'locais': o['include_local_variables']}))")

def test_configuracao_de_producao():
    r = subprocess.run([sys.executable, "-c", SCRIPT], env=os.environ | ENV_VERCEL, capture_output=True, text=True, cwd=BASE_DIR)
    c = json.loads(r.stdout)
    assert set(c["hosts"]) == {"helptoner-abc.vercel.app", "helptoner.vercel.app", "pedidos.helptoner.com.br"}
    assert "https://pedidos.helptoner.com.br" in c["csrf"]
    assert (c["idade"], c["cursores"], c["ssl"], c["prepare"]) == (0, True, "require", None)
    assert c["ip"] == "x-vercel-forwarded-for"
    assert (c["pii"], c["corpo"], c["locais"]) == (False, "never", False)

def test_sentry_nao_leva_dados_pessoais():
    evento = {"user": {"email": "carla@x.com"}, "request": {"url": "https://h/pedidos/?busca=João", "method": "GET",
              "cookies": {"sessionid": "x"}, "headers": {"Cookie": "x"}, "data": {"nome": "João"}, "query_string": "busca=João"}}
    assert limpar_evento(evento, {}) == {"request": {"url": "https://h/pedidos/", "method": "GET"}}

def test_build_so_migra_na_previa():
    rodar = Mock()
    main({"VERCEL_ENV": "production", "DATABASE_URL": "a"}, rodar)
    rodar.assert_not_called()
    main({"VERCEL_ENV": "preview", "DATABASE_URL": "pooler", "DATABASE_URL_DIRETA": "direta"}, rodar)
    args, kwargs = rodar.call_args
    assert args[0][-2:] == ["migrate", "--noinput"] and kwargs["env"]["DATABASE_URL"] == "direta" and kwargs["check"]
```

- [ ] **Step 2: Rodar e ver falhar.** `uv run pytest tests/seguranca`.
- [ ] **Step 3: Implementar**
  - Em `producao.py`:
    - `ALLOWED_HOSTS`: os valores existentes de `VERCEL_PROJECT_PRODUCTION_URL`, `VERCEL_BRANCH_URL` e `VERCEL_URL` (variáveis de sistema da Vercel) mais os de `DJANGO_ALLOWED_HOSTS`. `CSRF_TRUSTED_ORIGINS = ["https://" + h for h in ALLOWED_HOSTS]`.
    - Banco: a conexão com pooler do Neon (`DATABASE_URL`), com `CONN_MAX_AGE = 0`, `DISABLE_SERVER_SIDE_CURSORS = True`, `sslmode=require` e `OPTIONS["prepare_threshold"] = None` (o PgBouncer do Neon roda em modo transação).
    - `ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "x-vercel-forwarded-for"`; `STORAGES["staticfiles"]` com `whitenoise.storage.CompressedManifestStaticFilesStorage`; `LOGGING` para o console (`helptoner` em INFO e `django.request` em ERROR).
    - Sentry, só se houver `SENTRY_DSN`: `sentry_sdk.init(dsn=..., environment=os.environ.get("VERCEL_ENV", "producao"), send_default_pii=False, max_request_body_size="never", include_local_variables=False, traces_sample_rate=0.0, before_send=limpar_evento)`.
  - `erro_500`: usa `sentry_sdk.last_event_id()` como código de referência quando existir; senão, o código local.
  - `vercel.json`:

    ```json
    {
      "$schema": "https://openapi.vercel.sh/vercel.json",
      "regions": ["gru1"],
      "functions": { "config/wsgi.py": { "maxDuration": 30 } },
      "git": { "deploymentEnabled": { "main": false } }
    }
    ```

  - `.vercelignore`: `tests/`, `docs/`, `tailwind/`, `.github/`, `.ferramentas/`, `test-results/`.
  - `pyproject.toml`: `[tool.vercel.scripts]` com `build = "python scripts/vercel_build.py"`. A Vercel roda o `collectstatic` sozinha, porque `STATIC_ROOT` existe. O script só roda `python manage.py migrate --noinput` quando `VERCEL_ENV == "preview"`, usando `DATABASE_URL_DIRETA` se existir.
  - `.env.exemplo`: documentar `VERCEL_*`, `DATABASE_URL_DIRETA` e `SENTRY_DSN`.
- [ ] **Step 4: Rodar e ver passar.** `uv run pytest` (inclusive o `check --deploy` da Tarefa 3).
- [ ] **Step 5: Commit.** `git commit -m "chore: configuração de produção para Vercel, Neon e Sentry"`

### Tarefa 29: Integração contínua e atualizações automáticas

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/dependabot.yml`

- [ ] **Step 1: Escrever o `ci.yml`**

```yaml
name: CI
on: { push: {}, pull_request: {}, workflow_call: {} }
concurrency: { group: "ci-${{ github.ref }}", cancel-in-progress: true }
permissions: { contents: read }
jobs:
  testes:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    services:
      postgres:
        image: postgres:18
        env: { POSTGRES_USER: helptoner, POSTGRES_PASSWORD: helptoner, POSTGRES_DB: helptoner }
        ports: ["5432:5432"]
        options: --health-cmd "pg_isready -U helptoner" --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      DATABASE_URL: postgres://helptoner:helptoner@localhost:5432/helptoner
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v6
        with: { enable-cache: true }
      - run: uv python install 3.14
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run python scripts/css.py --conferir
      - run: uv run pytest
      - run: uv run playwright install --with-deps chromium
      - run: uv run pytest -m e2e
      - run: uv run pip-audit
      - name: check --deploy
        env: { DJANGO_SETTINGS_MODULE: config.settings.producao, DJANGO_ALLOWED_HOSTS: pedidos.exemplo.com.br }
        run: DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" uv run python manage.py check --deploy --fail-level WARNING
```

(Antes, rodar `uv add --dev pip-audit`.)

- [ ] **Step 2: Escrever o `dependabot.yml`** com dois blocos semanais: `package-ecosystem: uv` e `package-ecosystem: github-actions`, ambos em `directory: /`.

- [ ] **Step 3: Conferir localmente** os mesmos comandos, na ordem: `uv run ruff check .`, `uv run ruff format --check .`, `uv run python scripts/css.py --conferir`, `uv run pytest`, `uv run pytest -m e2e` e `uv run pip-audit`. Todos passam.

- [ ] **Step 4: Commit e verificação no GitHub.** `git commit -m "ci: testes, lint, auditoria e check --deploy a cada envio"`. Depois de o Lucas autorizar o envio, `git push` e conferir em Actions que o CI ficou verde. Se o `pip-audit` acusar uma falha sem correção disponível, pare e avise o Lucas.

### Tarefa 30: Botão "Publicar", backups e teste de restauração

**Files:**
- Create: `.github/actions/backup/action.yml`, `.github/workflows/publicar.yml`, `.github/workflows/backup.yml`, `.github/workflows/teste-restauracao.yml`

**Interfaces:**
- Consumes: o `ci.yml` (Tarefa 29), por `workflow_call`.
- Produces: o action composto `./.github/actions/backup`, com as entradas `nome`, `database-url` e `senha`, que instala o `postgresql-client-18` (repositório PGDG: `postgresql-common` e o script `apt.postgresql.org.sh -y`), roda `pg_dump --format=custom --no-owner --no-privileges "$URL" -f backup.dump`, cifra com `gpg --batch --yes --pinentry-mode loopback --passphrase "$SENHA" --symmetric --cipher-algo AES256 -o backup.dump.gpg backup.dump` e envia `backup.dump.gpg` com `actions/upload-artifact@v4` (`name: ${{ inputs.nome }}`, `retention-days: 30`). Segredos do GitHub usados: `DATABASE_URL_DIRETA` (a conexão direta, sem pooler, do banco de produção no Neon), `DJANGO_SECRET_KEY`, `BACKUP_SENHA`, `VERCEL_TOKEN`, `VERCEL_ORG_ID` e `VERCEL_PROJECT_ID`.

- [ ] **Step 1: Escrever o `publicar.yml`** (`on: workflow_dispatch`; `concurrency: { group: publicar, cancel-in-progress: false }`; todo job com `if: github.ref == 'refs/heads/main'`), com os jobs em sequência, na ordem de §10:
  1. `testes`: `uses: ./.github/workflows/ci.yml`.
  2. `backup` (`needs: testes`): checkout e `./.github/actions/backup` com `nome: backup-antes-de-publicar-${{ github.run_id }}`.
  3. `migrar` (`needs: backup`): setup do uv e do Python 3.14, `uv sync --locked --no-dev` e `uv run --no-dev python manage.py migrate --noinput`, com `DJANGO_SETTINGS_MODULE=config.settings.producao`, `DATABASE_URL=${{ secrets.DATABASE_URL_DIRETA }}`, `DJANGO_SECRET_KEY` e `DJANGO_ALLOWED_HOSTS=localhost`.
  4. `publicar` (`needs: migrar`): `npx --yes vercel@latest deploy --prod --yes --token "$VERCEL_TOKEN"`, com `VERCEL_ORG_ID` e `VERCEL_PROJECT_ID` no ambiente; guarda a URL que o comando imprime e confere com `curl -fsS "$URL/saude/"`.

- [ ] **Step 2: Escrever o `backup.yml`**: `schedule: cron "0 6 * * *"` (03:00 em Brasília) e `workflow_dispatch`; um passo calcula a data (`date +%F`) e chama o action com `nome: backup-<data>`.

- [ ] **Step 3: Escrever o `teste-restauracao.yml`**: `schedule: cron "0 9 1 * *"` e `workflow_dispatch`; `permissions: { actions: read, contents: read }`; serviço `postgres:18`. Passos:
  1. `ID=$(gh run list --workflow backup.yml --status success --limit 1 --json databaseId -q '.[0].databaseId')`;
  2. `gh run download "$ID" --dir restauracao` (com `GH_TOKEN: ${{ github.token }}`);
  3. decifrar com `gpg --batch --pinentry-mode loopback --passphrase "$BACKUP_SENHA" -d … > backup.dump`;
  4. `pg_restore --no-owner --no-privileges -d postgres://helptoner:helptoner@localhost:5432/helptoner backup.dump`;
  5. `uv sync --locked` e, com o `DATABASE_URL` local, `uv run python manage.py shell -c "from apps.pedidos.models import Pedido; from apps.cadastros.models import Cliente, Produto; print(Pedido.objects.count(), Cliente.objects.count(), Produto.objects.count())"`. O job falha se algum passo falhar (o GitHub avisa por e-mail).

- [ ] **Step 4: Commit.** `git commit -m "ci: publicação com backup antes, backup noturno e teste mensal de restauração"`. A execução de verdade acontece na Tarefa 31, depois de criados os segredos.

### Tarefa 31: Contas, primeira publicação e guia de operação

Esta tarefa precisa do Lucas: as contas são dele e os segredos não passam pelo chat.

**Files:**
- Create: `docs/operacao.md`
- Modify: `CLAUDE.md` (seção "Estado atual")

- [ ] **Step 1: Criar as contas e os recursos** (Lucas, com o passo a passo no guia):
  - **Neon** (conta própria, no site do Neon e não pelo Marketplace da Vercel): projeto em `aws-sa-east-1`, PostgreSQL 18, computação fixa em 0,25 CU; branch `main` (produção) e branch `previa`; extensão `unaccent` disponível. Guardar as conexões com e sem pooler de cada branch.
  - **Vercel** (Hobby): projeto ligado ao repositório. Variáveis de **Production**: `DJANGO_SETTINGS_MODULE=config.settings.producao`, `DJANGO_SECRET_KEY` (nova, com 50 caracteres ou mais), `DATABASE_URL` (Neon `main`, com pooler), `ADMIN_URL` (caminho difícil de adivinhar, terminado em "/") e `SENTRY_DSN`. Variáveis de **Preview**: as mesmas, com outra `DJANGO_SECRET_KEY` e o banco `previa` (`DATABASE_URL` com pooler e `DATABASE_URL_DIRETA`). Deixar ativada a opção de expor as variáveis de sistema.
  - **Sentry** (plano gratuito): projeto Django, alerta por e-mail a cada novo erro.
  - **GitHub, segredos de Actions:** `DATABASE_URL_DIRETA` (Neon `main`, sem pooler), `DJANGO_SECRET_KEY` (a mesma da produção), `BACKUP_SENHA` (guardada também fora do GitHub, porque sem ela o backup não abre), `VERCEL_TOKEN`, `VERCEL_ORG_ID` e `VERCEL_PROJECT_ID`.

- [ ] **Step 2: Primeira publicação.** Rodar o workflow "Publicar" em Actions, com a branch `main`. Esperado: os quatro jobs verdes e `/saude/` respondendo `{"status": "ok"}` na URL `*.vercel.app`.

- [ ] **Step 3: Primeiro administrador.** No computador do Lucas, com as variáveis de produção só naquele terminal (`DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY` e `DATABASE_URL` com a conexão direta), rodar `uv run python manage.py criar_primeiro_admin --email <e-mail> --nome "<nome>"`. Entrar no sistema publicado, fazer o primeiro acesso completo e cadastrar o segundo administrador (o pai do Lucas) pela tela Funcionários.

- [ ] **Step 4: Monitoramento e backups.** No cron-job.org, criar um teste em `https://<endereço>/saude/` a cada 5 minutos, com aviso por e-mail quando falhar. Rodar `backup.yml` e `teste-restauracao.yml` manualmente uma vez; os dois precisam ficar verdes.

- [ ] **Step 5: Escrever o `docs/operacao.md`**, em linguagem simples, com estas seções:
  1. Como rodar localmente (ambiente, `.env.local`, `migrate`, `runserver`, `scripts/css.py --observar`, testes).
  2. Como publicar (o botão "Publicar"; migrações precisam funcionar também com a versão anterior do código no ar, porque o `migrate` roda antes da publicação).
  3. Como restaurar um backup (restauração do Neon para um momento das últimas 6 horas e restauração do arquivo noturno com `gpg` e `pg_restore`).
  4. Como criar o primeiro administrador.
  5. Como trocar segredos (chave do Django, senha do banco, token da Vercel, senha do backup).
  6. Contas e onde fica cada configuração.
  7. Limites gratuitos a acompanhar (§10) e onde ver o consumo.
  8. Plano B: Render (§5.5).
  9. Atualizações (Dependabot, correções de segurança do Django, migração para o Django 6.2 em abril de 2027).
  10. Arquivos de terceiros e as suas versões (HTMX, Inter, Tailwind).

- [ ] **Step 6: Conferência final** (anotar o resultado no guia):
  - login com 2FA funcionando em produção;
  - um pedido de teste do começo ao fim (depois cancelado);
  - `python manage.py check --deploy` sem alertas;
  - um erro de teste chegando ao Sentry sem dados pessoais;
  - tempo da primeira tela depois de 15 minutos parado (medir e anotar, conforme o risco de §12);
  - consumo do primeiro dia na Vercel e no Neon.

- [ ] **Step 7: Atualizar o `CLAUDE.md`** (estado atual: sistema publicado, endereço e próximos passos) e fazer o commit: `git commit -m "docs: guia de operação e primeira publicação"`.
