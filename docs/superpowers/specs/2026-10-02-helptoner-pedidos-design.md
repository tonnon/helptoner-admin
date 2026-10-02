# Sistema de Pedidos Helptoner: especificação de design

- **Data:** 02/10/2026
- **Status:** aguardando revisão
- **Substitui:** `Desktop/app.py` (aplicativo desktop em Tkinter + SQLite)
- **Esboços visuais aprovados:** `docs/esbocos/` (abrem direto no navegador)
  - `identidade-visual-v3.html`: identidade e tela de novo pedido
  - `telas.html`: demais telas
  - `relatorios.html`: relatórios

---

## 1. Contexto e objetivo

A Helptoner emite pedidos de venda num aplicativo desktop (`app.py`). A revisão encontrou problemas que afetam dinheiro e estoque:

- estoque negativo;
- total da tela diferente do total gravado;
- desconto sem validação;
- número de pedido duplicado;
- formato de moeda misturado;
- cadastros sem validação;
- carrinho apagado sem aviso;
- vínculos entre tabelas não aplicados.

Também faltam operações básicas: não dá para editar cadastros, repor estoque, cancelar pedido ou gerar PDF.

**Objetivo:** substituir o app por um sistema web seguro, moderno e responsivo, que a equipe use pelo navegador, no computador ou no celular.

**Usuários:** hoje são 2 administradores (Lucas e o pai). Outros funcionários (vendedores) podem entrar depois.

**Restrições:**
- desenvolvido e mantido por uma pessoa só (com apoio do Claude), sem equipe;
- precisa rodar na **Vercel**;
- a prioridade é a melhor qualidade e segurança possíveis;
- o uso é comercial.

**Critérios de sucesso:**
1. Pedidos saem pelo navegador com total e estoque sempre corretos, inclusive com acessos simultâneos.
2. Só quem tem login, com verificação em duas etapas, acessa o sistema, e cada perfil vê só o que pode.
3. Os relatórios mostram faturamento, lucro e margem que batem com os pedidos.
4. Uma pessoa sozinha consegue manter, atualizar e restaurar o sistema seguindo a documentação.

## 2. Escopo

### Primeira versão

- Login com verificação em duas etapas, primeiro acesso guiado e área "Minha conta".
- Funcionários com perfis Administrador e Vendedor.
- Clientes (pessoa física ou jurídica) e produtos.
- Pedidos: rascunho, confirmação, cancelamento, PDF e "Repetir pedido".
- Estoque com movimentos (entrada com custo, ajuste, saída e devolução) e custo médio.
- Início com rascunhos, últimos pedidos e números do mês.
- Relatórios completos, com lucro e margem, exportados para Excel e PDF.
- Histórico de alterações e de logins.
- Publicação, backup, monitoramento e documentação.

### Fora da primeira versão

- Condição de pagamento, comissão, alerta de estoque mínimo, envio por e-mail ou WhatsApp e nota fiscal.
- Envio de e-mails pelo sistema. Se alguém esquecer a senha, o administrador a redefine.
- Migração de dados do `app.py`: não há dados reais a migrar.

## 3. Regras de negócio

### 3.1 Ciclo do pedido

| Status | Significado | Estoque |
|---|---|---|
| **Rascunho** | Em montagem. Fica salvo no servidor a cada mudança e não tem número. | Não muda |
| **Confirmado** | Recebe o número, grava os totais e o custo de cada item. | Baixa |
| **Cancelado** | Registra quem cancelou, quando e o motivo (obrigatório). | Volta |

- **Confirmação** é uma operação única no banco: ou tudo é gravado, ou nada é. A sequência é:
  1. travar as linhas dos produtos do pedido, em ordem de `id`, para evitar travamento cruzado entre duas confirmações;
  2. conferir o estoque de cada produto;
  3. gerar o número do pedido;
  4. gravar o custo de cada item;
  5. registrar os movimentos de saída;
  6. gravar os totais e mudar o status.
- **Número do pedido:** sequencial, único e sem buracos. É gerado por um contador numa linha travada durante a confirmação; rascunhos abandonados não consomem número. Aparece como "nº 1.042".
- **Data:** é a data e hora da confirmação, gravada em UTC e exibida no fuso de Brasília (America/Sao_Paulo). Não pode ser editada.
- **Pedido confirmado** não pode ser editado nem excluído. Para corrigir, cancela e emite outro.
- **Cancelar** é exclusivo do Administrador e exige confirmação e motivo.
- **Rascunho** só pode ser editado por quem o criou ou por um Administrador. Todos podem vê-lo. Pode ser excluído enquanto for rascunho.
- **Repetir pedido** cria um rascunho com o mesmo cliente e os mesmos itens, usando os **preços atuais**. Vale para qualquer pedido confirmado ou cancelado.

### 3.2 Itens

- **Quantidade:** sempre inteira e maior que zero.
- **Mesmo produto adicionado de novo:** soma na mesma linha. Existe uma restrição de unicidade para o par (pedido, produto).
- **Estoque no rascunho:** a conferência considera o total do produto no pedido. Ela aparece como aviso no rascunho e é obrigatória na confirmação.
- **Preço:** vem do cadastro do produto e não pode ser alterado no pedido.
- **Dados copiados para o item:** código, descrição e preço unitário são copiados ao adicionar. O custo unitário é copiado na confirmação. Mudanças posteriores no produto não alteram pedidos.

### 3.3 Desconto

- Vale para o pedido inteiro e pode ser em **R$** ou em **%**.
- São gravados o tipo, o valor informado e o valor final em R$.
- **Validação:** 0 ≤ desconto em R$ ≤ subtotal. Em %, fica entre 0 e 100.
- **Arredondamento:** meio para cima, com 2 casas decimais. O cálculo usa `Decimal`, nunca `float`.
- O total da tela é sempre calculado pelo servidor e é o mesmo que será gravado.

### 3.4 Estoque

- O estoque atual fica no produto, como número inteiro maior ou igual a zero. O banco garante isso com uma regra `CHECK`.
- O estoque **só muda por movimentos**, todos registrados com usuário, data e hora:

| Tipo | Origem | Quem faz | Exige |
|---|---|---|---|
| Inicial | Implantação do produto | Administrador | Quantidade e custo unitário |
| Entrada | Compra ou reposição | Administrador | Quantidade, custo unitário e observação (ex.: nº da nota) |
| Saída por pedido | Confirmação | Sistema | — |
| Devolução por cancelamento | Cancelamento | Sistema | — |
| Ajuste (+ ou −) | Perda, avaria, contagem | Administrador | Quantidade e motivo |

- Cada movimento guarda o estoque e o custo médio resultantes, para poder auditar.

### 3.5 Custo médio

- **Entrada, ou estoque inicial:**
  `novo_custo = (estoque_atual × custo_atual + qtd × custo_entrada) ÷ (estoque_atual + qtd)`
- **Saída por pedido:** o custo médio não muda, e o item grava o custo médio daquele momento.
- **Devolução por cancelamento:** volta ao estoque pelo custo gravado no item, que entra na média como uma entrada.
- **Ajuste:** não muda o custo médio. O ajuste positivo entra pelo custo médio atual.
- **Estoque zerado:** o custo médio continua com o último valor.
- **Precisão:** 4 casas decimais no custo e 2 em valores monetários.

### 3.6 Lucro e margem

- **Receita líquida do item** = total do item − parte do desconto que cabe a ele. O desconto é dividido proporcionalmente ao valor de cada item; a diferença de centavos fica no último item.
- **Lucro bruto** = receita líquida − (quantidade × custo unitário gravado).
- **Margem** = lucro bruto ÷ receita líquida.
- Relatórios consideram só pedidos **confirmados**. Os cancelados têm relatório próprio.

### 3.7 Clientes

- **Tipo:** Pessoa (CPF) ou Empresa (CNPJ).
- **Documento:** guardado só com os dígitos, com validação dos dígitos verificadores e sem duplicidade.
- **Obrigatórios:** tipo, documento e nome ou razão social.
- **Opcionais:** telefone, e-mail, endereço completo (CEP, logradouro, número, complemento, bairro, cidade e UF) e observações.
- **Código:** gerado automaticamente.
- **Exclusão:** clientes são inativados, nunca excluídos. Inativos não aparecem na busca do pedido.

### 3.8 Produtos

- **Código:** digitado pelo usuário e guardado em maiúsculas, sem espaços nas pontas. É único (ex.: `CE285A`).
- **Demais campos:** descrição, marca e preço de venda.
- **Somente leitura:**
  - o **estoque**, que só muda por movimentos;
  - o **custo médio**, que só o Administrador vê.
- **Exclusão:** produtos são inativados, nunca excluídos.

## 4. Usuários e segurança

### 4.1 Perfis

| Funcionalidade | Vendedor | Administrador |
|---|:---:|:---:|
| Cadastrar e editar clientes | ✅ | ✅ |
| Montar, confirmar e repetir pedidos | ✅ | ✅ |
| Ver todos os pedidos e gerar PDF | ✅ | ✅ |
| Consultar produtos e estoque (sem custo) | ✅ | ✅ |
| Cadastrar e editar produtos e preços | ❌ | ✅ |
| Entrada, estoque inicial e ajuste | ❌ | ✅ |
| Cancelar pedidos | ❌ | ✅ |
| Ver custo, lucro e margem | ❌ | ✅ |
| Relatórios | ❌ | ✅ |
| Gerenciar funcionários | ❌ | ✅ |
| Histórico de alterações e logins | ❌ | ✅ |

- As permissões são verificadas **no servidor em cada ação** (views e serviços). Esconder botões é só conforto visual.
- **Números do Início:** o Administrador vê os números da empresa; o Vendedor vê os números dos pedidos que ele emitiu.

### 4.2 Contas e acesso

- **Não existe cadastro público.** O Administrador cria o funcionário com nome, e-mail e perfil, e o sistema gera uma senha temporária, mostrada uma única vez.
- **Primeiro acesso obrigatório**, garantido por um middleware que bloqueia o uso até concluir:
  1. trocar a senha temporária;
  2. configurar o aplicativo autenticador (TOTP, por QR code);
  3. receber os códigos de recuperação.
- **Login:**
  - e-mail e senha, seguidos do código de 6 dígitos;
  - **verificação em duas etapas obrigatória para todos**;
  - limite de tentativas erradas por conta e por IP, que bloqueia temporariamente com aviso claro.
- **Senhas:**
  - no mínimo 12 caracteres;
  - recusa de senhas comuns e parecidas com os dados do usuário;
  - guardadas com hash **Argon2**.
- **Sessão:** expira depois de **2 horas sem uso**. O cookie é `Secure`, `HttpOnly` e `SameSite=Lax`.
- **Funcionário desativado** perde o acesso na hora (as sessões são invalidadas). O histórico dele é mantido.
- **Ações do Administrador sobre funcionários:** redefinir senha (gera nova senha temporária) e zerar a verificação em duas etapas (celular perdido).

### 4.3 Proteções técnicas

- **Login exigido em tudo:** `LoginRequiredMiddleware` do Django; as exceções são marcadas explicitamente (login e página de saúde).
- **Ataques comuns:**
  - CSRF em todos os formulários e requisições HTMX;
  - escape automático nos templates;
  - acesso ao banco só pelo ORM ou com parâmetros, nunca com SQL montado com texto do usuário.
- **Cabeçalhos de segurança:**
  - HSTS, com redirecionamento para HTTPS;
  - **CSP nativa do Django 6**, sem scripts nem estilos inline e sem `eval`. O HTMX roda com `allowEval: false` e `includeIndicatorStyles: false`, sem atributos `hx-on`;
  - `X-Frame-Options: DENY`, `Referrer-Policy`, `nosniff` e COOP.
- **Painel administrativo do Django:** fica num endereço não padrão, só para o superusuário, e passa pelo mesmo login com verificação em duas etapas. É usado só para manutenção.
- **Segredos** (chave do Django, banco e Sentry) ficam nas variáveis de ambiente da Vercel, nunca no código. O arquivo `.env.local` fica no `.gitignore`.
- **Arquivos externos:** nenhum script ou fonte vem de site de terceiros; HTMX, fontes Inter e CSS são servidos pelo próprio sistema.
- **Auditoria:**
  - `django-simple-history` em clientes, produtos e usuários, com valor anterior e novo;
  - registro de logins com e sem sucesso (data, e-mail e navegador);
  - movimentos de estoque e eventos do pedido já guardam o autor.
- **LGPD (básico):**
  - dados pessoais só para usuários logados;
  - banco criptografado no armazenamento e na transmissão;
  - dados hospedados no Brasil (Neon em São Paulo);
  - os alertas de erro não levam dados pessoais.
- `python manage.py check --deploy` sem alertas é condição para publicar.

## 5. Arquitetura

### 5.1 Tecnologias

| Parte | Escolha |
|---|---|
| Linguagem e framework | Python 3.14 + **Django 6.1**. Migrar para o **6.2, de suporte longo**, em abril de 2027 |
| Banco | **PostgreSQL 18** no **Neon**, região **São Paulo** (`aws-sa-east-1`), ligado pelo Marketplace da Vercel |
| Hospedagem | **Vercel Pro**, com suporte nativo a Django e função na região `gru1` (São Paulo) |
| Telas | Templates do Django com template partials + **HTMX 2** (arquivo local) + um pouco de JavaScript próprio |
| Visual | **Tailwind CSS 4**, compilado pelo executável standalone, sem Node.js. O CSS gerado vai no repositório |
| Login e 2FA | **django-allauth**, com o módulo de verificação em duas etapas (`mfa`) |
| Senhas | `argon2-cffi` |
| Histórico | `django-simple-history` |
| PDF | **fpdf2**, só em Python |
| Excel | **openpyxl** |
| Gráficos | Módulo próprio em JavaScript que desenha SVG, sem biblioteca externa (ver seção 7) |
| Arquivos estáticos | WhiteNoise no ambiente local; na Vercel, CDN com `collectstatic` automático |
| Pacotes | **uv**, com `pyproject.toml` e `uv.lock` (versões fixas e conferência de integridade) |
| Testes | pytest + pytest-django; **Playwright** para fluxos completos no navegador |
| Qualidade | ruff (estilo e formatação) e pip-audit (falhas de segurança conhecidas nos pacotes) |
| Erros e monitoramento | **Sentry** (plano gratuito) e **UptimeRobot** (plano gratuito) |

### 5.2 Como as peças se conectam

```
Navegador ──HTTPS──► Vercel (gru1)
                      ├─ CDN: CSS, JS, fontes e logo
                      └─ Função Python: Django ──TLS (conexão com pooler)──► Neon PostgreSQL 18 (sa-east-1)
                                         └──► Sentry (erros, sem dados pessoais)
```

- **Configuração do banco:** usa a conexão com pooler do Neon, `CONN_MAX_AGE = 0` e `DISABLE_SERVER_SIDE_CURSORS = True`.
- **Nada é gravado em disco.** Os arquivos PDF e Excel são gerados na memória e enviados direto ao navegador.

### 5.3 Organização do código

```
helptoner-pedidos/
├── manage.py
├── pyproject.toml / uv.lock
├── vercel.json                  # região gru1, duração máxima da função
├── config/                      # settings (base, local, produção), urls, wsgi
├── apps/
│   ├── core/                    # layout, formatação em real e datas, permissões, páginas de erro, saúde
│   ├── contas/                  # usuário, perfis, primeiro acesso, 2FA, funcionários, registro de logins
│   ├── cadastros/               # clientes e produtos (validação de CPF e CNPJ)
│   ├── estoque/                 # movimentos e custo médio (services.py)
│   ├── pedidos/                 # rascunho, confirmação, cancelamento, repetição, PDF (services.py)
│   └── relatorios/              # consultas agregadas, exportação Excel e PDF
├── templates/                   # base, componentes e partials do HTMX
├── static/                      # css gerado, htmx.min.js, js próprio, fontes, logo
├── tailwind/                    # fonte do CSS (entrada do Tailwind)
├── tests/                       # unitários, integração e e2e (Playwright)
└── docs/                        # especificação, plano e guia de operação
```

- **Regras de negócio** ficam em `services.py` de cada app, que são funções puras de domínio e transações. As views só tratam entrada e saída. Os testes das regras não dependem de telas.
- **Telas com HTMX:** cada interação devolve só um pedaço da página (template partial). Exemplos: adicionar item, buscar com sugestões e recalcular o total.

### 5.4 Ambientes

| Ambiente | Banco | Uso |
|---|---|---|
| Local (Windows) | PostgreSQL 18 instalado no Windows | Desenvolvimento e testes |
| Prévia (Vercel Preview) | Cópia separada no Neon (branch) | Ver mudanças antes de publicar. Nunca usa dados reais |
| Produção | Neon, branch principal | Uso real |

## 6. Telas e identidade visual

### 6.1 Identidade

- **Cores do logo:**
  - **Azul Toner `#0200FF`** para ações, links e foco. Em botões com texto branco, o contraste é bom.
  - **Vermelho Help `#FF0000`** para a marca, o menu ativo e destaques.
  - **Vermelho escuro `#D60000`** para textos de erro e ações perigosas, porque fica legível.
- **Degradê vermelho → azul**, como nas setas do logo, numa faixa no topo e na borda do resumo.
- **Cores neutras:** tinta `#0E1024`, fundo `#F5F6FB` e cartões brancos.
- **Estados:**
  - verde `#0B8A5E`: confirmado;
  - âmbar `#A15C07`: rascunho;
  - vermelho-escuro: cancelado.
- **Fonte Inter**, servida pelo próprio sistema. Números em colunas usam algarismos de largura fixa.
- **Logo:** o PNG oficial (`docs/assets/logo-helptoner.png`), no menu lateral e no topo da versão de celular.
- **Movimento:**
  - animações de até 0,5 s;
  - esqueleto de carregamento no primeiro carregamento;
  - avisos que somem sozinhos;
  - tudo desligado automaticamente com a opção "reduzir movimento" do sistema.

### 6.2 Padrões

- **Menu:** lateral no computador; no celular vira barra no topo.
- **Tabelas:** viram cartões no celular. Na tela de pedido, o celular mostra uma barra fixa com o total e o botão de confirmar.
- **Buscas com sugestões** (cliente, produto): resultado parcial destacado; uso pelas setas e Enter; itens indisponíveis aparecem bloqueados com o motivo.
- **Erros de validação:** aparecem ao lado do campo, com uma leve animação.
- **Ações sérias:** cancelar, desativar e ajustar estoque pedem confirmação.
- **Telas vazias:** sempre trazem orientação ("Nenhum cliente ainda. Cadastre o primeiro.").
- **Acessibilidade:** foco sempre visível, contraste adequado e rótulos em todos os campos.

### 6.3 Inventário de telas

| Tela | Acesso | Conteúdo principal |
|---|---|---|
| Login + verificação em duas etapas | Todos | E-mail e senha, código de 6 dígitos, link para código de recuperação |
| Primeiro acesso | Todos | Nova senha → autenticador (QR) → códigos de recuperação |
| Minha conta | Todos | Trocar senha, gerar novos códigos de recuperação |
| Início | Todos | Novo pedido, rascunhos em aberto, últimos pedidos, números do mês (ver 4.1) |
| Lista de pedidos | Todos | Busca por número ou cliente; filtros de status e período; quem emitiu; paginação |
| Novo pedido / rascunho | Todos | Como em `identidade-visual-v3.html`: cliente, produtos, quantidade, − / +, desconto em R$ ou %, observações, resumo fixo |
| Detalhe do pedido | Todos (cancelar: Administrador) | Dados, itens, totais, histórico, PDF, Repetir pedido, Cancelar com motivo |
| Clientes (lista e formulário) | Todos | Busca, Pessoa ou Empresa, CPF/CNPJ com máscara e validação, endereço, inativar |
| Produtos (lista e formulário) | Consulta: todos; edição: Administrador | Código, descrição, marca, preço, estoque (selo de cor), custo médio (só Administrador) |
| Estoque | Consulta: todos; movimentos: Administrador | Histórico com filtros; Entrada (com custo), Estoque inicial, Ajuste (com motivo) |
| Relatórios | Administrador | Ver seção 7 |
| Funcionários | Administrador | Lista, novo, perfil, 2FA ativo ou pendente, redefinir senha, zerar 2FA, desativar |
| Histórico de alterações | Administrador | Quem mudou o quê e quando; logins com e sem sucesso |
| Páginas de erro (403, 404, 500) | Todos | No visual do sistema, com caminho de volta |

## 7. Relatórios

- **Acesso:** só o Administrador.
- **Filtros:** ficam numa linha acima de tudo e valem para a página inteira.
  - **Período**, com atalhos: últimos 3 meses, 2026 até agora, últimos 12 meses e datas personalizadas.
  - **Agrupamento:** dia, semana ou mês.
  - **Funcionário.**
- **Comparação:** os indicadores mostram a variação em relação ao período anterior equivalente.
- **Exportação:** todo relatório exporta para **Excel** (openpyxl) e **PDF** (fpdf2) com os filtros aplicados.

| Aba | Conteúdo |
|---|---|
| Resumo | Indicadores (faturamento líquido, lucro bruto, margem, pedidos, valor médio por pedido); gráfico de faturamento e lucro no tempo; produtos que mais faturaram; clientes sem comprar há mais de 60 dias |
| Vendas por período | Pedidos, bruto, descontos, líquido, lucro, margem e valor médio por dia, semana ou mês |
| Clientes | Ranking por valor; número de pedidos; último pedido; lucro; clientes sem comprar há X dias (X ajustável) com atalho para "Repetir pedido" |
| Produtos e marcas | Quantidade, faturamento, lucro, margem e participação no total, por produto e por marca |
| Funcionários | Pedidos, valor, lucro e desconto médio concedido por quem emitiu |
| Estoque | Quantidade atual, valor do estoque a custo médio, produtos zerados, entradas, saídas e ajustes no período |
| Cancelamentos | Pedidos cancelados, valor, motivos e quem cancelou |

**Regras dos gráficos**, já aplicadas e conferidas em `relatorios.html`:
- **Cores das séries:** azul da marca `#0200FF` e laranja `#eb6834`. A combinação foi aprovada pelo validador de cores para daltonismo e contraste.
- **Uma escala só por gráfico.** Medidas de unidades diferentes vão em gráficos separados.
- **Marcas e rótulos:** linhas de 2 px, barras de no máximo 24 px com ponta arredondada, legenda e rótulos diretos só nos pontos finais.
- **Interação:** mira vertical com caixa de valores ao passar o mouse e também pelo teclado.
- **Toda visualização tem a versão em tabela.**
- **Ao trocar o filtro**, a tela fica no lugar, levemente apagada, até os novos números chegarem, sem esqueleto e sem pular.

## 8. Tratamento de erros

| Situação | Comportamento |
|---|---|
| Dado inválido (campo) | Mensagem ao lado do campo; nada é gravado |
| Regra de negócio violada (estoque, desconto, permissão) | Mensagem clara na tela; a operação inteira é desfeita |
| Duas confirmações disputando o mesmo estoque | O banco trava os produtos: a primeira confirma e a segunda recebe "Estoque insuficiente" com os números atualizados |
| Sem permissão | Página 403 no visual do sistema; o acesso fica registrado |
| Sessão expirada no meio do pedido | O rascunho já está salvo; depois do login, volta ao pedido |
| Erro inesperado | Página 500 amigável com código de referência; alerta por e-mail via Sentry, sem dados pessoais |
| Falha ao gerar PDF ou Excel | Aviso na tela; o erro vai para o Sentry |

## 9. Testes

Cada regra recebe o teste **antes** do código. Os testes rodam no PostgreSQL, igual à produção.

- **Unitários e de integração das regras:**
  - estoque nunca negativo, inclusive com **duas confirmações simultâneas** em threads;
  - soma do mesmo produto na mesma linha;
  - totais, desconto (R$ e %) e arredondamento;
  - custo médio em todos os tipos de movimento;
  - cancelamento devolvendo estoque e custo;
  - numeração única e sem buracos;
  - divisão do desconto entre os itens e o lucro resultante;
  - validação de CPF e CNPJ;
  - "Repetir pedido" com preços atuais.
- **Permissões:**
  - todas as URLs exigem login;
  - todas as ações exclusivas do Administrador devolvem 403 para o Vendedor;
  - custo e lucro nunca aparecem no HTML do Vendedor;
  - rascunho de outro usuário não pode ser editado pelo Vendedor.
- **Segurança:**
  - `check --deploy` sem alertas;
  - os cabeçalhos (CSP, HSTS, frame) estão presentes;
  - o painel administrativo exige a verificação em duas etapas;
  - o primeiro acesso não pode ser pulado.
- **Relatórios:** números conferidos com um conjunto de pedidos conhecido. A exportação para Excel e PDF gera arquivos válidos.
- **Fluxos completos (Playwright):**
  - login com verificação em duas etapas;
  - montar pedido com busca, confirmar, gerar PDF e cancelar;
  - entrada de estoque;
  - exportar relatório.

## 10. Operação

- **Repositório:** privado no GitHub. O `.gitignore` exclui `.superpowers/` (esboços) e `.env.local` (segredos).
- **A cada envio de código**, o GitHub Actions roda: ruff, testes (com PostgreSQL), pip-audit e `check --deploy`.
- **Publicação em produção:** é uma ação manual, o botão "Publicar" no GitHub Actions, que executa nesta ordem:
  1. testes;
  2. **backup** do banco;
  3. `migrate`;
  4. publicação na Vercel pela linha de comando da Vercel.

  As prévias continuam automáticas, sempre com o banco de prévia.
- **Backups:**
  - restauração para um momento recente, recurso do próprio Neon;
  - cópia criptografada todas as noites (`pg_dump`) guardada por 30 dias;
  - teste de restauração automático uma vez por mês.
- **Monitoramento:**
  - UptimeRobot verifica a página `/saude/` a cada 5 minutos e avisa por e-mail;
  - Sentry avisa por e-mail quando há erro.
- **Atualizações:**
  - o Dependabot abre propostas de atualização semanais;
  - as atualizações de segurança do Django são aplicadas assim que saem;
  - a migração para o Django 6.2 (suporte longo) acontece em abril de 2027.
- **Endereço:** começa com o endereço `*.vercel.app`. Se vocês tiverem o domínio `helptoner.com.br`, depois passa para `pedidos.helptoner.com.br`.
- **Documentação** (`docs/operacao.md`): como rodar localmente, publicar, restaurar backup, criar o primeiro administrador e trocar segredos.
- **Custos previstos:**
  - Vercel Pro: US$ 20/mês, 1 assento;
  - Neon: plano gratuito para começar; avaliar o plano pago se precisar de mais histórico de restauração ou de mais capacidade;
  - Sentry e UptimeRobot: gratuitos.

## 11. Modelo de dados (resumo)

| Entidade | Campos principais | Regras no banco |
|---|---|---|
| **Usuario** (modelo próprio, login por e-mail) | nome, e-mail, ativo, deve_trocar_senha, grupos (Administrador ou Vendedor) | e-mail único |
| **Cliente** | codigo (automático), tipo (PF/PJ), nome, documento (só dígitos), telefone, email, cep, logradouro, numero, complemento, bairro, cidade, uf, observacoes, ativo | documento único |
| **Produto** | codigo, descricao, marca, preco (12,2), custo_medio (14,4), estoque (inteiro), ativo | codigo único; `CHECK estoque >= 0`; `CHECK preco >= 0` |
| **MovimentoEstoque** | produto, tipo, quantidade (> 0), custo_unitario (14,4), estoque_apos, custo_medio_apos, pedido (opcional), usuario, motivo, criado_em | `CHECK quantidade > 0` |
| **ContadorPedido** | ultimo_numero | linha única, travada na confirmação |
| **Pedido** | numero (vazio no rascunho), status, cliente, criado_por, confirmado_por/em, cancelado_por/em, motivo_cancelamento, desconto_tipo, desconto_informado, desconto_valor, subtotal, total, observacoes | numero único quando preenchido |
| **ItemPedido** | pedido, produto, codigo, descricao, quantidade, preco_unitario, custo_unitario (na confirmação), desconto_rateado | único (pedido, produto); `CHECK quantidade > 0` |
| **RegistroAcesso** | e-mail tentado, usuario (opcional), sucesso, ip, navegador, quando | — |
| Tabelas do histórico | geradas pelo django-simple-history para Cliente, Produto e Usuario | — |

Valores em dinheiro usam `DecimalField`. Datas são gravadas com fuso horário (UTC) e exibidas em America/Sao_Paulo.

## 12. Riscos e como reduzi-los

| Risco | Como reduzir |
|---|---|
| Suporte a Django na Vercel é recente (abril de 2026) | O app não guarda nada no servidor e segue a configuração padrão do Django, então pode ir para outra hospedagem (Railway, Render ou Docker) sem reescrever |
| Primeira tela lenta depois de um tempo sem uso | Função na região São Paulo, poucos pacotes e importações enxutas; medir após a publicação |
| Manutenção por uma pessoa só | Testes automáticos, publicação com um botão, guia de operação e atualizações automáticas |
| Perda de dados | Backups em duas camadas, teste mensal de restauração e backup antes de cada publicação |
| Celular do 2FA perdido | Códigos de recuperação; o Administrador pode zerar a verificação em duas etapas de outro usuário. Os dois administradores cobrem um ao outro |

## 13. Registro de decisões

| # | Decisão | Origem |
|---|---|---|
| 1 | Sistema web no lugar do desktop | Usuário |
| 2 | Django (Python) em vez de Next.js, pelo critério de qualidade e segurança | Comparação aprovada |
| 3 | Hospedagem na Vercel (plano Pro, uso comercial) | Usuário |
| 4 | Ciclo rascunho → confirmado → cancelado; confirmado não se edita | Parte 1 |
| 5 | Desconto no pedido, em R$ ou %, limitado ao subtotal | Parte 1 |
| 6 | Preço não editável no pedido; quantidade inteira; venda sem estoque bloqueada | Parte 1 |
| 7 | Código de produto digitado; código de cliente automático | Parte 1 |
| 8 | Perfis Administrador e Vendedor; o Administrador faz tudo o que o Vendedor faz | Parte 2 |
| 9 | Verificação em duas etapas obrigatória para todos; Vendedor vê todos os pedidos; sem e-mail na primeira versão; sessão de 2 h | Parte 2 |
| 10 | GitHub privado; pasta `Desktop\projects\helptoner-pedidos`; PostgreSQL local no Windows | Parte 3 |
| 11 | Identidade com o logo PNG oficial; layout com resumo ao lado; animações e esqueleto | Parte 4 |
| 12 | Busca com sugestões; mesmo produto soma na linha; ajuste com − / + | Parte 4 |
| 13 | Início com números do mês; "Repetir pedido" na primeira versão | Parte 4 |
| 14 | Relatórios completos na primeira versão, só para o Administrador | Parte 4 |
| 15 | Lucro e margem com custo por entrada e custo médio automático (opção A) | Parte 4 |
| 16 | Sentry e UptimeRobot gratuitos; publicação manual com backup antes; endereço `*.vercel.app` no início | Parte 5 |
| 17 | Rascunho editável só por quem criou ou pelo Administrador | Parte 5 |
| 18 | Números do Início: empresa para o Administrador; os próprios para o Vendedor | **Nova, definida nesta especificação: confirmar** |
| 19 | "Repetir pedido" usa os preços atuais | **Nova, definida nesta especificação: confirmar** |
