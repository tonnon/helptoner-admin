# Guia de operação do Helptoner Pedidos

Este guia explica como rodar, publicar, restaurar e manter o sistema. Os comandos podem ser copiados como estão. O que aparece entre `<` e `>` deve ser trocado pelo valor real, sem os sinais.

- `<domínio>`: o endereço de produção, sem `https://` (ex.: `helptoner-pedidos.vercel.app`).
- **Git Bash**: o terminal do Git no Windows. É onde ficam o Git e o atalho `linux`.
- **Terminal do Ubuntu**: o Linux do WSL, aberto com `wsl -d Ubuntu-24.04` no PowerShell ou no Windows Terminal.

Nunca coloque senha, chave ou conexão de banco num arquivo que vá para o Git, numa mensagem de commit ou num chat.

## 1. Como rodar localmente

### Como este computador está montado

- O Windows 11 está com o Smart App Control ligado, e ele bloqueia o PostgreSQL e o driver do banco (psycopg) nativos do Windows. Desligá-lo não tem volta. Por isso, tudo o que é Python roda no Linux: Ubuntu 24.04 no **WSL1** (o WSL2 não funciona nesta máquina sem mexer na BIOS).
- O código fica na pasta do Windows, `C:\Users\lucas\Desktop\projects\helptoner-admin`, que o Linux enxerga como `/mnt/c/Users/lucas/Desktop/projects/helptoner-admin`.
- No Ubuntu estão o uv, o Python 3.14 (instalado pelo uv) e o PostgreSQL 18. O ambiente virtual fica no disco do Linux, em `~/.venvs/helptoner`, e não na pasta do projeto: o `~/.profile` define `UV_PROJECT_ENVIRONMENT`.
- O `~/.profile` também liga o PostgreSQL se ele estiver parado e define `UV_CONCURRENT_INSTALLS=1`, porque no WSL1 o uv instalando vários pacotes ao mesmo tempo falha com "Cannot allocate memory". Se esse erro ainda aparecer, repita o comando.
- O Git roda no Windows (Git Bash), nunca dentro do Linux. A identidade pessoal está configurada só neste repositório:

```bash
git config user.name    # lucastonnon
git config user.email   # lucastonnon@gmail.com
```

- As mensagens de commit seguem o formato `tipo: descrição em português` (ex.: `fix: ...`, `feat: ...`, `docs: ...`).
- Os arquivos de texto usam fim de linha LF (`.gitattributes`). Editores no Windows devem manter LF.

### O atalho `linux`

No Git Bash, `linux "<comando>"` roda o comando no Ubuntu, já na pasta do projeto. Exemplos: `linux "uv sync"`, `linux "uv run pytest"`.

O atalho é o arquivo `C:\Users\lucas\.local\bin\linux`:

```bash
#!/usr/bin/env bash
# Roda um comando no Ubuntu (WSL1) dentro da pasta do projeto Helptoner.
# Uso: linux "uv run pytest -q"
MSYS_NO_PATHCONV=1 exec wsl.exe -d Ubuntu-24.04 --cd 'C:\Users\lucas\Desktop\projects\helptoner-admin' --exec bash -lc "$*"
```

O `bash -lc` carrega o `~/.profile`, então o venv, o uv e o PostgreSQL já estão prontos em cada comando.

### Banco local e `.env.local`

O banco local é o PostgreSQL 18 do Ubuntu, com o papel `helptoner` (que pode criar bancos, porque os testes criam o `test_helptoner`) e o banco `helptoner`. A extensão `unaccent` vem com o PostgreSQL, e a primeira migração a ativa.

O arquivo `.env.local`, na raiz do projeto, guarda a conexão local. Ele fica fora do Git (o `.gitignore` cobre `.env.*`). O sistema lê dele uma variável só:

```
DATABASE_URL=postgres://helptoner:<senha do papel helptoner>@localhost:5432/helptoner
```

Hoje ele também guarda, num comentário, a senha do superusuário do PostgreSQL local. As demais variáveis do `.env.exemplo` são de produção e não entram no `.env.local`.

### Comandos do dia a dia

```bash
linux "uv sync"                                  # instala ou atualiza os pacotes do uv.lock
linux "uv run python manage.py migrate"          # aplica as migrações no banco local
linux "uv run python manage.py runserver"        # sistema em http://localhost:8000
```

O WSL1 divide a rede com o Windows, então o navegador do Windows abre `http://localhost:8000`. Para parar o servidor, Ctrl+C.

Para entrar no sistema local, crie uma vez um usuário no banco local:

```bash
linux "uv run python manage.py criar_primeiro_admin --email <seu e-mail> --nome '<Seu nome>'"
```

O comando mostra uma senha temporária. No primeiro acesso, o sistema pede uma senha nova e o aplicativo autenticador, como em produção.

**CSS (Tailwind).** O `static/css/app.css` é gerado a partir de `tailwind/app.css` e das classes usadas em `templates/` e `static/js/`, e vai para o Git. Enquanto mexe em templates, deixe rodando num segundo Git Bash:

```bash
linux "uv run python scripts/css.py --observar"
```

No WSL1, o `--observar` às vezes não percebe mudanças feitas por programas do Windows. Se o visual não mudar, gere de novo à mão:

```bash
linux "uv run python scripts/css.py"
```

Na primeira vez, o script baixa o executável do Tailwind para `.ferramentas/` (fora do Git) e confere o SHA-256. Ele só roda no Linux x64. Classes usadas só em código Python (em `apps/`) não entram no CSS; se um dia precisar, acrescente `@source "../apps";` em `tailwind/app.css`.

### Testes e conferências antes de enviar

Antes de enviar (o CI repete quase tudo isso, mais os testes no navegador e o `check --deploy`):

```bash
linux "uv run ruff check ."
linux "uv run ruff format --check ."          # para corrigir: linux "uv run ruff format ."
linux "uv run python scripts/css.py --conferir"
linux "uv run python manage.py makemigrations --check --dry-run"
linux "uv run pytest"
linux "uv run pytest -m e2e --collect-only -q"
linux "uv run pip-audit"
```

- `uv run pytest` roda tudo menos os testes no navegador, no PostgreSQL local.
- Os testes no navegador (Playwright) **não rodam neste computador**: no WSL1, o Node que vem com o Playwright dá "Exec format error". Aqui só se confere que eles são coletados sem erro (`--collect-only`). Eles rodam de verdade no GitHub Actions, a cada envio. Se um falhar, o log do job no Actions mostra onde.

### Terminal de produção

Alguns comandos precisam falar com o banco real: criar o primeiro administrador, devolver o acesso ao painel, conferir o `check --deploy` e o teste do Sentry. Eles rodam num terminal do Ubuntu aberto só para isso, com as variáveis de produção só nele. No fim, feche o terminal.

1. No Git Bash, deixe a pasta na mesma versão que está no ar:

```bash
git switch main
git pull
```

2. Abra o terminal do Ubuntu (`wsl -d Ubuntu-24.04` no PowerShell) e rode:

```bash
cd /mnt/c/Users/lucas/Desktop/projects/helptoner-admin
export PS1="[PRODUCAO] $PS1"
export DJANGO_SETTINGS_MODULE=config.settings.producao
read -rsp "DJANGO_SECRET_KEY: " DJANGO_SECRET_KEY; echo; export DJANGO_SECRET_KEY
read -rsp "DATABASE_URL (Neon main, conexão direta): " DATABASE_URL; echo; export DATABASE_URL
```

- O `read -rsp` pede o valor sem mostrar na tela e sem gravar no histórico do terminal. Cole e tecle Enter.
- `DJANGO_SECRET_KEY` é a chave de produção (a mesma da Vercel e do GitHub).
- `DATABASE_URL` aqui é a conexão **direta** do branch `main` do Neon, sem `-pooler` no endereço: a mesma do segredo `DATABASE_URL_DIRETA` do GitHub.
- Quem migra a produção é o botão "Publicar". Não rode `migrate` neste terminal sem necessidade.
- O `manage.py shell` pode avisar que alguns objetos não foram importados automaticamente. Pode ignorar.
- No fim, `exit` fecha o terminal, e as variáveis somem junto.

### Se precisar preparar outro computador

1. No Windows: `wsl --set-default-version 1` e `wsl --install -d Ubuntu-24.04` (ou versão 2, se a máquina permitir).
2. No Ubuntu, o PostgreSQL 18 pelo repositório oficial (PGDG), o papel e o banco:

```bash
sudo apt update
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
sudo apt install -y postgresql-18
sudo -u postgres createuser --createdb --pwprompt helptoner
sudo -u postgres createdb --owner helptoner helptoner
```

3. O uv e o Python: `curl -LsSf https://astral.sh/uv/install.sh | sh` e depois `uv python install 3.14`.
4. No fim do `~/.profile`:

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/helptoner"
export PATH="$HOME/.local/bin:$PATH"
if ! pg_lsclusters -h 2>/dev/null | grep -q online; then sudo -n service postgresql start >/dev/null 2>&1; fi
export UV_CONCURRENT_INSTALLS=1
```

O `sudo -n` só liga o PostgreSQL se o usuário tiver sudo sem senha; senão, ligue à mão com `sudo service postgresql start`.

5. O `.env.local` com a `DATABASE_URL`, o atalho `linux` numa pasta do PATH do Git Bash e, por fim, `linux "uv sync"` e `linux "uv run pytest"`.

## 2. Como publicar

### O caminho de uma mudança

1. Trabalhe numa branch, não direto na `main`.
2. `git push` da branch. O GitHub Actions roda o CI: ruff, CSS em dia, testes com PostgreSQL 18, testes no navegador, `pip-audit` e `check --deploy`. A Vercel cria uma **prévia** da branch, com o banco de prévia (o build da prévia roda o `migrate` nesse banco). As prévias pedem login na Vercel para abrir.
3. Com o CI verde, junte a branch na `main` (por pull request, ou merge e `git push`).
4. Rode o **Publicar**.

Um `git push` na `main` **não publica** nada: o `vercel.json` desliga a publicação automática da `main`. Só o botão publica.

Para entrar no sistema de uma prévia, crie um usuário no banco de prévia: abra um terminal como o de produção, mas com a conexão direta do branch `previa` e a chave da prévia, e rode o `criar_primeiro_admin` (seção 4).

### O botão "Publicar"

GitHub → repositório → aba **Actions** → workflow **Publicar** → **Run workflow** → branch `main` → **Run workflow**.

Os jobs rodam em fila, e cada um só começa se o anterior passou:

1. `testes`: o mesmo CI de cada envio.
2. `backup`: confere se a variável `URL_PRODUCAO` existe, faz o backup cifrado do banco de produção e o guarda como artefato `backup-antes-de-publicar-<número da execução>`, por 30 dias.
3. `migrar`: roda o `migrate` no banco de produção, pela conexão direta (`DATABASE_URL_DIRETA`).
4. `publicar`: publica na Vercel (`vercel deploy --prod`) e confere `https://<domínio>/saude/`, que precisa responder `{"status": "ok"}`.

Detalhes:

- Rodado a partir de outra branch, nenhum job roda (todos ficam como ignorados).
- Duas execuções do Publicar nunca correm juntas: a segunda espera a primeira terminar.
- A conferência usa a variável `URL_PRODUCAO` do repositório, e não o endereço gerado pela publicação. Com a proteção padrão da Vercel (Standard Protection), os endereços gerados pedem login na Vercel; o domínio de produção é público. O endereço gerado aparece no log ("Publicado em: ...").
- Mudou uma variável na Vercel? Ela só vale numa publicação nova. Rode o Publicar.

### Migrações: precisam funcionar com o código anterior

O `migrate` roda **antes** de o código novo entrar no ar. Entre um passo e outro (e até a próxima publicação, se o passo da Vercel falhar), o código antigo roda com o banco novo. Por isso, toda migração precisa funcionar com o código que está no ar:

- **Coluna nova obrigatória:** use `db_default=` (valor padrão no próprio banco) ou `null=True`. O `default=` do Django existe só no Python, e o código antigo, que não conhece a coluna, falharia ao gravar.
- **Remover campo ou modelo:** em duas publicações. Primeiro, publique o código que não usa mais o campo; numa publicação seguinte, a migração que o remove.
- **Renomear campo ou tabela:** evite. Crie o novo, copie os dados, mude o código e remova o antigo depois, como acima.
- **Nova restrição (unique, check):** antes, garanta que os dados e o código atual já seguem a regra.
- **Migração de dados:** mantenha curta. O job `migrar` tem limite de 15 minutos.

### Se algo der errado

- **Falhou em `testes`:** nada mudou na produção. Corrija, envie e rode de novo.
- **Falhou em `backup`:** nada mudou. Veja a mensagem: `URL_PRODUCAO` vazia (crie a variável, seção 6) ou `DATABASE_URL_DIRETA` e `BACKUP_SENHA` errados.
- **Falhou em `migrar`:** o código antigo continua no ar. No PostgreSQL, cada migração é tudo ou nada; as anteriores da mesma execução ficam aplicadas. Corrija e publique de novo.
- **Falhou em `publicar`:** o banco já foi migrado e o código antigo continua no ar (por isso a regra acima). Veja o log. Token da Vercel vencido: seção 5.
- **Falhou a conferência do `/saude/`:** a versão nova pode estar no ar com problema. Abra `https://<domínio>/saude/` no navegador e veja os logs da função no painel da Vercel e o Sentry. Resposta 400 em tudo quase sempre é endereço não aceito: variáveis de sistema da Vercel desligadas (seção 6) ou domínio novo sem `DJANGO_ALLOWED_HOSTS`.
- **Versão nova com defeito:** o painel da Vercel permite voltar para a publicação anterior (Instant Rollback). Funciona porque as migrações são compatíveis com o código anterior. Depois de um rollback, confira no painel, no próximo Publicar, que a publicação nova ficou com o domínio de produção: a Vercel pode manter o domínio preso à versão anterior até o rollback ser desfeito.
- **Dados estragados:** seção 3.

## 3. Como restaurar um backup

### Qual caminho usar

- **Problema percebido em até 6 horas** (edição errada em massa, algo apagado): restauração do Neon (A). Volta o banco inteiro para o minuto escolhido.
- **Mais antigo, ou Neon indisponível:** arquivo noturno (B), ou o backup feito antes de uma publicação.
- **Só consultar dados antigos:** arquivo noturno restaurado numa cópia local (B, passo 5a), sem mexer na produção.

Restaurar a produção traz de volta o banco **inteiro**: tudo o que foi gravado depois do momento escolhido se perde (pedidos, clientes, movimentos de estoque). Anote o que foi feito depois desse momento para refazer à mão, e avise a família para não usar o sistema durante a restauração.

### A. Restauração do Neon (últimas 6 horas)

O plano gratuito do Neon guarda o histórico das últimas 6 horas.

1. Se der, rode antes o workflow **Backup** à mão (Actions → Backup → Run workflow), para guardar também o estado atual.
2. No console do Neon, abra o projeto, vá à área de restauração (backup/restore) e escolha o branch `main`.
3. Escolha a data e a hora (confira o fuso horário que a tela usa) e confirme.
4. O Neon costuma guardar o estado de antes da restauração como outro branch. Depois de conferir que está tudo certo, apague esse branch, para não ocupar a cota.
5. Abra o sistema e confira os últimos pedidos.

### B. Arquivo noturno (gpg e pg_restore)

Os backups ficam como artefatos do GitHub Actions por **30 dias**:

- `backup-AAAA-MM-DD`: workflow **Backup**, todo dia às 03:00 de Brasília;
- `backup-antes-de-publicar-<número>`: em cada execução do **Publicar**.

Cada artefato é um `.zip` com o arquivo `backup.dump.gpg`: o `pg_dump` do banco (formato custom, sem dono e sem permissões), cifrado com AES256 e a senha `BACKUP_SENHA`.

**1. Baixar.** Actions → Backup (ou Publicar) → a execução desejada → seção **Artifacts** → baixe o arquivo. Ele vai para a pasta Downloads do Windows.

**2. Levar para fora do projeto.** O backup tem dados de clientes. Trabalhe numa pasta do Linux, nunca dentro do projeto, porque o `.gitignore` não cobre esses arquivos. No terminal do Ubuntu:

```bash
mkdir -p ~/restauracao && cd ~/restauracao
python3 -m zipfile -e /mnt/c/Users/lucas/Downloads/backup-AAAA-MM-DD.zip .
ls -l     # deve aparecer backup.dump.gpg
```

**3. Decifrar.** O comando pede a `BACKUP_SENHA`:

```bash
gpg --output backup.dump --decrypt backup.dump.gpg
```

Se a caixa de senha não aparecer direito no terminal, use:

```bash
gpg --pinentry-mode loopback --output backup.dump --decrypt backup.dump.gpg
```

Backups feitos antes de uma troca da `BACKUP_SENHA` só abrem com a senha antiga (seção 5).

**4. Conferir o `pg_restore`.** O backup é do PostgreSQL 18, e um `pg_restore` mais antigo não lê o arquivo:

```bash
pg_restore --version     # precisa ser 18.x
```

Neste computador, ele já vem com o PostgreSQL 18. Em outra máquina Ubuntu com o repositório do PostgreSQL (PGDG): `sudo apt install postgresql-client-18`.

**5a. Restaurar numa cópia local, só para consultar.** Não mexe na produção:

```bash
sudo -u postgres createdb -O helptoner helptoner_restaurado
sudo -u postgres pg_restore --role=helptoner --no-owner --no-privileges -d helptoner_restaurado < backup.dump
sudo -u postgres psql -d helptoner_restaurado      # consulta em SQL; \q para sair
```

Quando terminar: `sudo -u postgres dropdb helptoner_restaurado`.

**5b. Restaurar na produção.** Substitui o banco inteiro:

1. Avise a família para não usar o sistema.
2. Rode o workflow **Backup** à mão, para guardar o estado atual, mesmo ruim.
3. No mesmo terminal do Ubuntu, informe a conexão direta do branch `main` do Neon e restaure:

```bash
read -rsp "DATABASE_URL (Neon main, conexão direta): " DATABASE_URL; echo; export DATABASE_URL
pg_restore --clean --if-exists --single-transaction --no-owner --no-privileges -d "$DATABASE_URL" backup.dump
```

`--clean --if-exists` apaga as tabelas antes de recriá-las. `--single-transaction` faz tudo ou nada: se der erro, o banco fica como estava.

4. Rode o **Publicar** logo em seguida. Ele faz um backup do estado restaurado, aplica as migrações que o backup ainda não tinha e publica. Até lá, se o backup for de antes de alguma migração, o sistema no ar pode dar erro.
5. Confira o sistema.

**6. Limpar.** Apague a pasta (`rm -rf ~/restauracao`) e o `.zip` da pasta Downloads.

### O que roda sozinho

- **Backup** (`backup.yml`): todo dia às 03:00 de Brasília e quando rodado à mão.
- **Backup antes de publicar:** dentro do Publicar.
- **Teste de restauração** (`teste-restauracao.yml`): todo dia 1º, às 06:00 de Brasília. Baixa o último backup bem-sucedido do workflow Backup, decifra, restaura num PostgreSQL 18 vazio e conta pedidos, clientes e produtos. Se falhar, o GitHub avisa por e-mail.
- Os artefatos somem depois de 30 dias.
- Os agendamentos só valem a partir da branch `main`. O GitHub pode atrasar execuções agendadas em horários de muito uso.

## 4. Como criar o primeiro administrador

### Criar (uma vez só)

Depois da primeira publicação, quando o banco já tem as tabelas, no terminal de produção (seção 1):

```bash
uv run python manage.py criar_primeiro_admin --email <seu e-mail> --nome "<Seu nome completo>"
```

O comando cria o usuário com o perfil Administrador e como superusuário (com acesso ao painel de manutenção) e mostra a senha temporária uma única vez; ela não fica gravada. Rode só uma vez: de novo, com outro e-mail, ele criaria outro superusuário. As demais pessoas são cadastradas pela tela Funcionários.

Depois, `exit`.

### Primeiro acesso e segundo administrador

1. Abra `https://<domínio>/` e entre com o e-mail e a senha temporária.
2. O sistema exige, em ordem: senha nova (12 caracteres ou mais), aplicativo autenticador (ler o QR code com o aplicativo do celular) e códigos de recuperação. Guarde os códigos fora do celular (gerenciador de senhas ou papel em lugar seguro). Cada código vale uma vez, se o celular sumir.
3. Menu **Funcionários** → **+ Novo funcionário**: nome, e-mail e perfil **Administrador**. O sistema mostra uma senha temporária uma única vez; repasse pessoalmente.
4. O segundo administrador faz o próprio primeiro acesso, com o celular dele.

Os dois administradores cobrem um ao outro: se um perder o celular, o outro usa **Zerar 2FA** na tela do funcionário; se um esquecer a senha, o outro usa **Redefinir senha**.

### Painel de manutenção

Fica em `https://<domínio>/<ADMIN_URL>` (o caminho da variável `ADMIN_URL` da Vercel). Só entra quem é superusuário **e** tem o perfil Administrador, pelo mesmo login com a verificação em duas etapas. É só para manutenção.

### Devolver o acesso ao painel

Quando um Administrador que não é superusuário usa **Zerar 2FA** ou **Redefinir senha** no superusuário, ou muda o perfil dele para Vendedor, o sistema tira do superusuário o acesso ao painel (`is_superuser` e `is_staff`). É de propósito: senão, qualquer Administrador poderia tomar a conta do superusuário e entrar no painel. O histórico registra "... e acesso ao painel removido". O acesso só volta pelo terminal:

1. Se o perfil virou Vendedor, peça ao outro Administrador que volte o perfil para Administrador na tela Funcionários (assim fica no histórico).
2. Conclua o primeiro acesso de novo (senha nova e/ou autenticador), se o sistema pedir.
3. No terminal de produção (seção 1):

```bash
uv run python manage.py shell
```

```python
from apps.contas.models import Usuario
u = Usuario.objects.get(email="<seu e-mail, em minúsculas>")
u.is_superuser = True
u.is_staff = True
u._change_reason = "Acesso ao painel devolvido pelo terminal"
u.save(update_fields=["is_superuser", "is_staff"])
print(u.perfil, u.is_superuser, u.is_staff)   # esperado: Administrador True True
exit()
```

### Se ninguém conseguir entrar

Se os dois administradores perderem o acesso (celular e códigos de recuperação, ou senha), o terminal resolve para uma conta de Administrador. No terminal de produção, `uv run python manage.py shell` e:

```python
from apps.contas.models import Usuario
from apps.contas.services import redefinir_senha, zerar_2fa
u = Usuario.objects.get(email="<e-mail, em minúsculas>")
zerar_2fa(u, por=u)                # perdeu o celular e os códigos
print(redefinir_senha(u, por=u))   # esqueceu a senha: mostra uma senha temporária nova
exit()
```

Use só a linha necessária. No próximo login, o sistema pede o primeiro acesso de novo. As duas ações ficam no histórico, e o acesso ao painel não muda.

## 5. Como trocar segredos

Para gerar um valor novo (no Git Bash):

```bash
linux "python3 -c 'import secrets; print(secrets.token_urlsafe(50))'"
```

O resultado tem 67 caracteres (letras, números, `-` e `_`). Guarde cada valor novo no gerenciador de senhas antes de colocá-lo no serviço: o GitHub não mostra um segredo depois de salvo.

| Segredo | Onde fica | Depois de trocar |
|---|---|---|
| `DJANGO_SECRET_KEY` | Vercel (Production) e GitHub, com o mesmo valor | Publicar; todos entram de novo |
| `DJANGO_SECRET_KEY` da prévia | Vercel (Preview) | Vale na próxima prévia |
| Senha do banco | Dentro de `DATABASE_URL` (Vercel) e `DATABASE_URL_DIRETA` (GitHub) | Publicar logo em seguida |
| `VERCEL_TOKEN` | GitHub | Apagar o token antigo na Vercel |
| `BACKUP_SENHA` | GitHub e gerenciador de senhas | Guardar a antiga por 30 dias |
| `ADMIN_URL` | Vercel (Production e Preview) | Publicar |
| `SENTRY_DSN` | Vercel (Production e Preview) | Publicar |

### Chave do Django (`DJANGO_SECRET_KEY`)

1. Gere uma chave nova (o comando acima gera 67 caracteres; precisa de 50 ou mais).
2. Vercel → configurações do projeto → Environment Variables → edite a `DJANGO_SECRET_KEY` de Production.
3. GitHub → Settings → Secrets and variables → Actions → `DJANGO_SECRET_KEY` → atualize com o mesmo valor.
4. Rode o Publicar.

Todos que estiverem logados saem e precisam entrar de novo (senha e código). Senhas, autenticadores e códigos de recuperação continuam valendo, porque não dependem da chave.

### Senha do banco (Neon)

1. Faça fora do horário de uso: a senha muda na hora, e o sistema no ar para de conectar até o passo 4.
2. No console do Neon, na parte de papéis (roles) do branch `main`, gere uma senha nova para o papel usado nas conexões.
3. Copie as duas conexões novas do `main` (com e sem pooler) e atualize:
   - Vercel, Production: `DATABASE_URL` (com pooler);
   - GitHub: `DATABASE_URL_DIRETA` (sem pooler).
4. Rode o Publicar. O backup e o `migrate` já usam a conexão direta nova, e a publicação leva a `DATABASE_URL` nova.

Se trocar também a senha no branch `previa`, atualize `DATABASE_URL` e `DATABASE_URL_DIRETA` de Preview na Vercel.

### Token da Vercel (`VERCEL_TOKEN`)

1. Vercel → configurações da conta → Tokens → crie um token novo. Escolha uma validade (por exemplo, 1 ano) e anote a data na agenda: um token vencido faz o job `publicar` falhar.
2. GitHub → segredo `VERCEL_TOKEN` → atualize.
3. Apague o token antigo na Vercel.

Não precisa publicar.

### Senha do backup (`BACKUP_SENHA`)

1. Gere uma senha nova: `linux "python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"`.
2. Guarde a nova no gerenciador de senhas, com a data da troca. **Guarde também a antiga:** os backups feitos antes da troca (que ficam até 30 dias) só abrem com ela.
3. GitHub → segredo `BACKUP_SENHA` → atualize.
4. Rode à mão o **Backup** e, depois que ele ficar verde, o **Teste de restauração**. Os dois verdes confirmam a senha nova.
5. Passados 30 dias, a senha antiga pode ser descartada.

### Caminho do painel (`ADMIN_URL`)

- Não pode ser vazio nem `admin` (com qualquer combinação de maiúsculas). Se for, o sistema não sobe, e todas as páginas dão erro.
- As barras no começo e no fim são opcionais: o sistema acerta para `caminho/`.
- Use letras, números, `-` e `_`, difícil de adivinhar. Para gerar: `linux "python3 -c 'import secrets; print(secrets.token_urlsafe(12))'"`.
- Sem `ADMIN_URL` na Vercel, o painel fica em `manutencao/`, fácil de adivinhar. Sempre defina.

Para trocar: mude na Vercel (Production e Preview) e rode o Publicar. O painel passa para `https://<domínio>/<novo caminho>/`.

### Endereço do Sentry (`SENTRY_DSN`)

Ele só permite enviar erros para o projeto, mas, se vazar: no Sentry, nas configurações do projeto (Client Keys), crie uma chave nova e desative a antiga; atualize `SENTRY_DSN` na Vercel (Production e Preview) e rode o Publicar.

## 6. Contas e onde fica cada configuração

### Resumo

| Serviço | Plano | Para quê | O que fica lá |
|---|---|---|---|
| GitHub (`tonnon/helptoner-admin`, privado) | Free | Código, CI, publicação, backups | Código; 6 segredos e a variável `URL_PRODUCAO` em Actions; artefatos de backup (30 dias); Dependabot |
| Vercel | Hobby | Hospedagem, com a função em São Paulo (`gru1`) | Projeto ligado ao repositório; variáveis de Production e Preview; domínio `*.vercel.app`; logs da função |
| Neon (conta própria) | Free | Banco PostgreSQL 18 em São Paulo | Projeto em `aws-sa-east-1`; branches `main` (produção) e `previa`; senha do banco; restauração das últimas 6 horas |
| Sentry | Gratuito | Avisos de erro por e-mail | Projeto Django; DSN; regra de alerta |
| cron-job.org | Gratuito | Saber se o sistema caiu | Teste de `/saude/` a cada 5 minutos, com aviso por e-mail |
| Gerenciador de senhas | — | Cópia dos segredos | `BACKUP_SENHA` (sem ela, o backup não abre), `DJANGO_SECRET_KEY`, `ADMIN_URL`, conexões do Neon, códigos de recuperação |

Ligue a verificação em duas etapas em todas essas contas: quem entra numa delas chega aos dados ou ao código.

### Onde fica cada variável

| Variável | Vercel Production | Vercel Preview | GitHub Actions | Para quê |
|---|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.producao` | `config.settings.producao` | — (fixa no workflow) | Obrigatória: sem ela, o build da Vercel usa as configurações locais e falha |
| `DJANGO_SECRET_KEY` | chave de produção | outra chave | segredo, igual ao de produção | Assinatura de sessões e formulários |
| `DATABASE_URL` | Neon `main`, com pooler | Neon `previa`, com pooler | — | Conexão do sistema |
| `DATABASE_URL_DIRETA` | — | Neon `previa`, sem pooler | segredo: Neon `main`, sem pooler | Migrações e backups |
| `ADMIN_URL` | caminho secreto | caminho secreto | — | Endereço do painel |
| `SENTRY_DSN` | DSN do Sentry | o mesmo DSN | — | Avisos de erro (a prévia aparece no Sentry como `preview`) |
| `DJANGO_ALLOWED_HOSTS` | só com domínio próprio | — | — | Endereços extras aceitos |
| `CABECALHO_IP_CLIENTE` | não usar | não usar | — | Só no plano B (seção 8) |
| `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` | — | — | segredos | Publicar pela linha de comando da Vercel |
| `BACKUP_SENHA` | — | — | segredo | Cifrar e decifrar os backups |
| `URL_PRODUCAO` | — | — | variável (não é segredo) | Conferência do `/saude/` no Publicar |

A Vercel também define sozinha `VERCEL_ENV`, `VERCEL_URL`, `VERCEL_BRANCH_URL` e `VERCEL_PROJECT_PRODUCTION_URL`. Os três últimos são os endereços que o sistema aceita; o `VERCEL_ENV=preview` faz o build da prévia migrar o banco de prévia. Por isso, a opção de expor as variáveis de sistema precisa ficar ligada.

### Passo a passo para criar as contas

A ordem importa: cada passo usa valores dos anteriores. Guarde cada valor no gerenciador de senhas assim que ele aparecer.

**1. Neon**, direto no site do Neon, com conta própria (não pelo Marketplace da Vercel, para o banco não depender da conta da Vercel):

1. Crie a conta e um projeto com PostgreSQL 18, na região AWS São Paulo (`aws-sa-east-1`).
2. Deixe a computação fixa em 0,25 CU (mínimo e máximo em 0,25). Mantenha o desligamento automático quando ninguém usa.
3. O branch padrão, `main`, é a produção. Crie o branch `previa` a partir dele **agora**, enquanto o `main` está vazio. Um branch nasce como cópia dos dados: nunca recrie a `previa` a partir do `main` depois que houver dados reais, porque a prévia nunca usa dados reais.
4. Deixe a computação da `previa` também em 0,25 CU.
5. De cada branch, copie as duas conexões: com pooler (o endereço tem `-pooler`) e direta (sem `-pooler`). São quatro no total.
6. A extensão `unaccent` já é oferecida pelo Neon, e a primeira migração a ativa. Não precisa fazer nada.

**2. Sentry:**

1. Crie a conta no plano gratuito e um projeto do tipo Django. Qualquer região de dados serve, porque os erros não levam dados pessoais.
2. Configure o aviso por e-mail a cada erro novo (o Sentry oferece isso ao criar o projeto; senão, crie uma regra de alerta).
3. Copie o DSN, nas configurações do projeto (Client Keys).

**3. Gerar os segredos** (no Git Bash):

```bash
linux "python3 -c 'import secrets; print(secrets.token_urlsafe(50))'"   # DJANGO_SECRET_KEY de produção
linux "python3 -c 'import secrets; print(secrets.token_urlsafe(50))'"   # DJANGO_SECRET_KEY da prévia
linux "python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"   # BACKUP_SENHA
linux "python3 -c 'import secrets; print(secrets.token_urlsafe(12))'"   # ADMIN_URL (use com uma barra no fim)
```

**4. Vercel:**

1. Crie a conta no plano Hobby (entrar com o GitHub é o mais simples).
2. Crie um projeto importando o repositório `tonnon/helptoner-admin`. Quando a Vercel pedir acesso ao GitHub, dê acesso só a esse repositório. O nome do projeto define o endereço `<nome>.vercel.app` (ex.: `helptoner-pedidos`).
3. Não mude as configurações de build: a região (`gru1`), a função e o build vêm do `vercel.json` e do `pyproject.toml`.
4. Se a Vercel tentar publicar logo na importação, pode falhar ou subir uma versão sem banco. Ignore: a primeira publicação de verdade é pelo botão Publicar.
5. Nas configurações do projeto, em Environment Variables, cadastre as variáveis da tabela acima, marcando os ambientes de cada uma conforme a tabela (Production, Preview ou os dois; não marque Development). **Nunca use uma conexão de produção em Preview:** o build da prévia roda `migrate` no banco de Preview.
6. Na mesma página, deixe ligada a opção de expor automaticamente as variáveis de sistema (System Environment Variables). Sem ela, o sistema não reconhece o próprio endereço e responde 400 a tudo, e a prévia não migra.
7. Proteção das publicações (Deployment Protection): deixe a padrão (Standard Protection). Prévias e endereços gerados pedem login na Vercel; o domínio de produção é público.
8. Anote o domínio de produção do projeto: é o `<domínio>` deste guia.
9. Token e IDs para o GitHub:
   - `VERCEL_TOKEN`: configurações da conta, em Tokens. Crie com validade (ex.: 1 ano) e anote a data na agenda.
   - `VERCEL_ORG_ID` e `VERCEL_PROJECT_ID`: o jeito mais simples é, no Git Bash, na pasta do projeto:

     ```bash
     npx --yes vercel@latest link
     cat .vercel/project.json      # "orgId" e "projectId"
     ```

     A pasta `.vercel/` fica fora do Git. Os dois IDs também aparecem nas configurações gerais da conta e do projeto, no painel da Vercel.

**5. GitHub** (repositório → Settings → Secrets and variables → Actions):

1. Aba de segredos (Secrets), um por um:
   - `DATABASE_URL_DIRETA`: Neon `main`, conexão direta;
   - `DJANGO_SECRET_KEY`: a mesma da Vercel Production;
   - `BACKUP_SENHA`;
   - `VERCEL_TOKEN`, `VERCEL_ORG_ID` e `VERCEL_PROJECT_ID`.
2. Aba de variáveis (Variables): `URL_PRODUCAO` = `https://<domínio>`, com `https://` e sem barra no fim (ex.: `https://helptoner-pedidos.vercel.app`).
3. Nas configurações de notificação do GitHub, mantenha o aviso por e-mail de falhas do Actions: é assim que um backup ou um teste de restauração com falha chega até você.
4. Nas configurações de segurança do repositório, ligue os alertas do Dependabot (avisos de falhas de segurança nos pacotes). As atualizações semanais já estão em `.github/dependabot.yml`.

**6. Código na `main`.** O botão Publicar e os agendamentos só existem quando os arquivos estão na branch `main` do GitHub. Junte a branch de trabalho na `main` e envie.

**7. Primeira publicação** (seção 2). Esperado: os quatro jobs verdes e `/saude/` respondendo `{"status": "ok"}`.

**8. Primeiro administrador** (seção 4).

**9. cron-job.org:**

1. Crie a conta gratuita.
2. Crie um teste para `https://<domínio>/saude/`, a cada 5 minutos.
3. Ligue o aviso por e-mail quando a execução falhar.

O `/saude/` não consulta o banco: esses acessos não acordam o Neon nem gastam a cota dele.

**10. Backup e teste de restauração.** Actions → Backup → Run workflow (branch `main`). Depois que ele ficar verde, Actions → Teste de restauração → Run workflow. Os dois precisam ficar verdes. O teste usa o último Backup bem-sucedido; o backup feito pelo Publicar não conta.

**11. Conferência final:** última seção deste guia.

### Domínio próprio (mais tarde)

Para passar a `pedidos.helptoner.com.br`:

1. Acrescente o domínio no projeto da Vercel e crie no registro do `helptoner.com.br` o apontamento de DNS que a Vercel indicar.
2. Na Vercel, em Production, defina `DJANGO_ALLOWED_HOSTS=pedidos.helptoner.com.br,<projeto>.vercel.app`, para os dois endereços funcionarem.
3. Atualize `URL_PRODUCAO` no GitHub e o endereço no cron-job.org.
4. Rode o Publicar.

Não inscreva o domínio na lista de pré-carregamento do HSTS (hstspreload.org): ela vale para o `helptoner.com.br` inteiro e é difícil de desfazer.

## 7. Limites gratuitos a acompanhar

Valores conferidos em 03/10/2026. Os planos mudam: confira de tempos em tempos. Passar de um limite pode parar o serviço até o mês seguinte.

| Serviço | Limite gratuito por mês | O que mais consome | Onde ver |
|---|---|---|---|
| Vercel Hobby | 4 horas de CPU ativa, 1 milhão de execuções e 100 GB de transferência | Cada página e cada pedaço HTMX é uma execução; PDF e Excel gastam CPU | Painel da Vercel, página de uso (Usage) da conta |
| Neon | 1 GB de dados e 100 CU-horas de computação | Tempo com o banco ligado. Com 0,25 CU, 100 CU-horas dão 400 horas ligado. O banco desliga sozinho alguns minutos depois da última consulta | Console do Neon: painel do projeto e página de uso ou cobrança |
| Sentry | 5 mil erros | Um erro que se repete em laço | Sentry, página de estatísticas de uso |
| GitHub Actions (repositório privado) | Minutos e armazenamento da conta gratuita (no plano Free, 2.000 minutos e 500 MB) | Cada envio roda o CI completo, com os testes no navegador; os backups ocupam armazenamento por 30 dias | Configurações da conta dona do repositório, parte de cobrança (Billing) |

No primeiro mês, olhe toda semana. Depois, uma vez por mês.

## 8. Plano B: Render

Se a Vercel pausar o projeto ou mudar as regras do plano Hobby, o sistema vai para o Render gratuito sem ser reescrito: ele não guarda nada no servidor e segue a configuração padrão do Django.

O que foi conferido em 03/10/2026:

- **Termos:** o Render não proíbe uso comercial no plano gratuito.
- **Serviço:** serviço web gratuito com Docker (Python 3.14, uv e Gunicorn), com o WhiteNoise servindo os arquivos estáticos. Máquina de 512 MB e 0,1 CPU, com 750 horas grátis por mês.
- **Região:** o Render não tem servidor no Brasil. O mais próximo fica na Virgínia (EUA). O banco precisa ir para lá também: com o banco em São Paulo, cada consulta atravessaria o continente.
- **Sono:** o serviço dorme depois de 15 minutos sem acesso e leva cerca de 1 minuto para acordar.
- **Reinícios:** o Render pode reiniciar o serviço gratuito a qualquer momento. Nada se perde: o rascunho é salvo a cada mudança, e a confirmação grava tudo ou nada.

### Como migrar

1. **LGPD.** Os dados passam a ficar nos EUA. A LGPD permite a transferência internacional nos casos do art. 33. Antes de migrar, confira os termos de proteção de dados (DPA) do Render e do Neon e registre o fundamento.
2. **Banco.** Crie um projeto novo no Neon na região AWS Virgínia (EUA), com PostgreSQL 18, 0,25 CU e os branches `main` e `previa` (a região de um projeto do Neon não muda depois de criado). Avise a família, rode o Backup e restaure o arquivo no projeto novo, como na seção 3 (passo 5b, com a conexão direta do projeto novo).
3. **Código.** Hoje o repositório não tem o que o Render precisa. Falta:
   - o Gunicorn: `linux "uv add gunicorn"`;
   - um `Dockerfile` com Python 3.14 e uv, que rode `uv sync --locked --no-dev` e o `collectstatic` no build e suba `gunicorn config.wsgi` na porta que o Render informa (variável `PORT`). O `collectstatic` carrega as configurações de produção, então precisa de valores provisórios de `DJANGO_SECRET_KEY` e `DATABASE_URL` durante o build. O WhiteNoise já está no sistema e serve os arquivos depois do `collectstatic`;
   - no `publicar.yml`, trocar o passo da Vercel pelo gancho de publicação (deploy hook) do Render, guardado como segredo, e desligar a publicação automática do Render, para continuar valendo "só o botão publica".
4. **Variáveis no Render:** `DJANGO_SETTINGS_MODULE=config.settings.producao`, `DJANGO_SECRET_KEY`, `DATABASE_URL` (Neon novo, com pooler), `ADMIN_URL`, `SENTRY_DSN`, `DJANGO_ALLOWED_HOSTS=<serviço>.onrender.com` (lá não existem as variáveis da Vercel; sem esta, tudo responde 400) e `CABECALHO_IP_CLIENTE` (abaixo).
5. **GitHub:** atualize `DATABASE_URL_DIRETA` (conexão direta do Neon novo) e `URL_PRODUCAO` (`https://<serviço>.onrender.com`). Apague os segredos da Vercel quando não forem mais usados.
6. **cron-job.org:** atualize o endereço do `/saude/`. Para evitar o sono, dá para criar um segundo teste a cada 10 minutos no horário da loja. Os termos do Render proíbem "contornar restrições de uso", então isso fica numa zona cinzenta: se o Render reclamar, desligue esse teste.
7. Rode o Publicar e refaça a conferência final (última seção).

### `CABECALHO_IP_CLIENTE`

O sistema usa o IP de quem tenta entrar para limitar tentativas de login por IP e para o histórico de acessos. Na Vercel, o IP real vem no cabeçalho `x-vercel-forwarded-for`, que é o padrão. No Render:

- **Sem a variável:** o sistema procura `x-vercel-forwarded-for`, que não existe lá, e **todo login responde 403**.
- **Com o nome do cabeçalho certo:** o ideal. Confira na documentação do Render qual cabeçalho traz o IP real do cliente sem que o navegador consiga forjá-lo.
- **Vazia (`CABECALHO_IP_CLIENTE=`):** o sistema usa o endereço da conexão (`REMOTE_ADDR`), que no Render é o do intermediário do Render, e não o do usuário. O login funciona, mas o limite por IP passa a contar todo mundo junto (várias senhas erradas de uma pessoa podem bloquear o login de todos por alguns minutos), e o histórico de acessos grava o IP do intermediário. O limite por conta (por e-mail) continua funcionando.
- **Não use `x-forwarded-for`:** ele pode trazer uma lista de endereços (e aí o login dá 403), e o navegador consegue pôr valores falsos nele.

## 9. Atualizações

### Dependabot (toda semana)

O `.github/dependabot.yml` abre propostas (pull requests) semanais para os pacotes Python (`uv`: `pyproject.toml` e `uv.lock`) e para as ações do GitHub Actions (`github-actions`). Para cada uma:

1. Espere o CI verde na proposta. A Vercel também cria uma prévia.
2. Se mudou o primeiro número da versão, leia as notas da versão do pacote antes.
3. Junte na `main`. Depois, rode o Publicar (dá para juntar várias atualizações numa publicação).
4. CI vermelho: investigue numa branch. Não junte proposta com CI vermelho.

O passo da Vercel no `publicar.yml` usa sempre a versão mais nova da linha de comando da Vercel (`vercel@latest`). Se uma mudança dela quebrar a publicação, fixe uma versão no workflow (`vercel@<versão>`).

### Correções de segurança do Django

O Django anuncia as correções de segurança com antecedência, no blog e na lista de e-mails django-announce. Assine a lista e aplique a correção assim que sair, sem esperar o Dependabot:

```bash
git switch -c django-seguranca
linux "uv lock --upgrade-package django"
linux "uv sync"
linux "uv run pytest"
git commit -am "chore: Django com correção de segurança"
git push -u origin django-seguranca
```

Com o CI verde, junte na `main` e rode o Publicar.

### `pip-audit` no CI

O CI roda o `pip-audit` a cada envio e dentro do Publicar. Se um pacote usado tiver falha de segurança conhecida, o CI falha e **o Publicar para**. Quase sempre, a solução é atualizar o pacote: `linux "uv lock --upgrade-package <pacote>"`. Se ainda não houver correção, avalie se a falha atinge o sistema. Se decidir aceitar por enquanto, acrescente `--ignore-vuln <ID da falha>` à linha do `pip-audit` em `.github/workflows/ci.yml`, com um comentário explicando o motivo, e tire quando a correção sair.

### Django 6.2 (abril de 2027)

O Django 6.2 sai em abril de 2027, com suporte longo. A 6.1 deixa de receber correções alguns meses depois (pela política do Django, quando sair a versão seguinte à 6.2; confira a data na página de versões do Django). Roteiro:

1. Ainda na 6.1, rode `linux "uv run pytest"` e leia o resumo de avisos (warnings) no fim: os avisos de recurso obsoleto mostram o que vai quebrar.
2. Leia as notas da versão 6.2 (mudanças incompatíveis).
3. Numa branch: no `pyproject.toml`, troque `django>=6.1,<6.2` por `django>=6.2,<6.3`; rode `linux "uv lock --upgrade-package django"` e `linux "uv sync"`. Confira se django-allauth, django-simple-history e os demais pacotes já aceitam a 6.2, e atualize junto se precisar.
4. Testes, CI verde (inclusive no navegador), prévia conferida, junte na `main` e rode o Publicar.
5. Atualize as menções ao Django 6.1 na documentação.

## 10. Arquivos de terceiros

Nenhum arquivo vem de outro site em produção: a política de segurança de conteúdo (CSP) bloqueia scripts e fontes de fora. Os arquivos de terceiros ficam no repositório, e o registro de cada um (origem, SHA-256 e licença) está em `static/vendor/VERSOES.txt`. Atualize esse arquivo a cada troca.

| Arquivo | Versão | Onde está |
|---|---|---|
| HTMX | 2.0.11 | `static/vendor/htmx.min.js`, carregado em `templates/base.html` (licença 0BSD) |
| Inter, para as telas | 4.1 (fonte variável) | `static/fontes/InterVariable.woff2` e `static/fontes/OFL.txt`, declarada em `tailwind/app.css` |
| Inter, para os PDFs | 4.1 (Regular e SemiBold) | `apps/core/pdf_recursos/Inter-Regular.ttf`, `Inter-SemiBold.ttf` e `OFL.txt` |
| Tailwind CSS | 4.3.3 (executável `tailwindcss-linux-x64`) | Baixado por `scripts/css.py` para `.ferramentas/` (fora do Git). Só no desenvolvimento e no CI; não vai para o navegador |

As duas cópias da Inter vêm do mesmo arquivo da versão 4.1 e usam a licença SIL Open Font License 1.1.

### Como atualizar

**HTMX.** Fique na série 2.0.x; uma versão principal nova exige revisão das telas. No terminal do Ubuntu, na pasta do projeto:

```bash
curl -fsSLo static/vendor/htmx.min.js https://unpkg.com/htmx.org@<versão>/dist/htmx.min.js
sha256sum static/vendor/htmx.min.js
curl -fsSL https://registry.npmjs.org/htmx.org/-/htmx.org-<versão>.tgz | tar -xzO package/dist/htmx.min.js | sha256sum
```

Os dois SHA-256 precisam ser iguais (o arquivo baixado e o do pacote oficial); se não forem, desfaça no Git Bash com `git checkout -- static/vendor/htmx.min.js`. Mantenha a configuração do `templates/base.html` (`allowEval: false`, `includeIndicatorStyles: false`, `historyCacheSize: 0` e `refreshOnHistoryMiss: true`): ela é necessária para a CSP sem scripts embutidos e para o navegador não guardar páginas com dados de clientes. Rode os testes; os testes no navegador rodam no CI.

**Inter.** Baixe `https://github.com/rsms/inter/releases/download/v<versão>/Inter-<versão>.zip`, anote o SHA-256 do zip e copie `web/InterVariable.woff2` para `static/fontes/` e `extras/ttf/Inter-Regular.ttf` e `extras/ttf/Inter-SemiBold.ttf` para `apps/core/pdf_recursos/`. Atualize os `OFL.txt` se a licença mudar. Rode os testes (os de PDF usam as fontes).

**Tailwind.** Em `scripts/css.py`, troque `VERSAO` e `SHA256` (o SHA-256 do `tailwindcss-linux-x64` publicado na página da versão no GitHub). Gere o CSS com `linux "uv run python scripts/css.py"`, confira o visual e faça o commit do `static/css/app.css` novo. Fique na série 4.x. O CI confere com `--conferir` que o CSS do repositório é o que o Tailwind gera.

## Primeira publicação — registro

Preencher depois da primeira publicação.

- Data:
- Endereço de produção:
- Execução do Publicar (número):

### Login com verificação em duas etapas em produção

Saia e entre de novo com e-mail, senha e o código do aplicativo autenticador.

Resultado:

### Pedido de teste do começo ao fim, depois cancelado

Cadastre um produto de teste (ex.: código `TESTE`) com estoque inicial e um cliente de teste (com um CPF de teste válido, como 123.456.789-09). Monte o pedido, confirme, gere o PDF e cancele com o motivo "Pedido de teste". Depois, inative o produto e o cliente.

Esse pedido fica para sempre como o nº 1, cancelado: a numeração não tem buracos, e pedidos não são apagados. O produto e o cliente de teste também ficam no histórico, inativos.

Resultado:

### `check --deploy` sem alertas

No terminal de produção (seção 1), com o endereço e o caminho do painel iguais aos da Vercel:

```bash
export DJANGO_ALLOWED_HOSTS=<domínio>
read -rsp "ADMIN_URL: " ADMIN_URL; echo; export ADMIN_URL
uv run python manage.py check --deploy --fail-level WARNING
```

Esperado: `System check identified no issues (0 silenced).`

Resultado:

### Erro de teste no Sentry, sem dados pessoais

No terminal de produção:

```bash
read -rsp "SENTRY_DSN: " SENTRY_DSN; echo; export SENTRY_DSN
uv run python manage.py shell -c "
import sentry_sdk
try:
    raise RuntimeError('Teste do Sentry. DETAIL: Key (documento)=(12345678909) already exists.')
except RuntimeError as erro:
    sentry_sdk.capture_exception(erro)
sentry_sdk.flush()
"
```

Esperado: o e-mail do Sentry e um erro novo `RuntimeError: Teste do Sentry.`, **sem** o trecho `DETAIL: ...` (onde apareceria um CPF) e sem dados de usuário. Depois, marque o erro como resolvido. Quando aparecer o primeiro erro de verdade, abra-o e confira que também não há usuário, cookies, cabeçalhos nem parâmetros de busca.

Resultado:

### Tempo da primeira tela depois de 15 minutos parado

Depois de 15 minutos sem ninguém usar o sistema, abra `https://<domínio>/` (já logado) com as ferramentas do navegador abertas (F12, aba Rede) e anote o tempo até o Início aparecer completo, com os números do mês. É nessa hora que o banco do Neon acorda. O cron-job.org acessa o `/saude/` a cada 5 minutos, mas essa página não usa o banco.

Resultado:

### Consumo do primeiro dia

Resultado na Vercel (execuções, CPU ativa e transferência):

Resultado no Neon (CU-horas e armazenamento):
