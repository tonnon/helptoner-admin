# Helptoner Pedidos

Sistema web de pedidos de venda da Helptoner (empresa familiar de toners). Substitui o app desktop antigo (`app.py`, Tkinter + SQLite), que tinha bugs de estoque, desconto e numeração.

## Estado atual (03/10/2026)

- **Design aprovado** em 5 partes: regras de negócio, usuários e segurança, arquitetura, telas, operação.
- **Especificação aprovada** por Lucas em 03/10/2026: `docs/superpowers/specs/2026-10-02-helptoner-pedidos-design.md`. A revisão de 03/10/2026 trouxe a regra de custo zero: hospedagem na Vercel gratuita (Hobby), com o Render como plano B (decisão 20).
- **Plano de implementação** escrito em 03/10/2026, aguardando a revisão de Lucas: `docs/superpowers/plans/2026-10-03-helptoner-pedidos.md` (8 etapas, 31 tarefas). A seção "Decisões tomadas neste plano" lista o que a especificação não fixava; a P1 (CNPJ alfanumérico) ajusta a regra de §3.7.
- **Próximo passo:** Lucas revisar o plano e escolher o modo de execução (subagentes ou na própria sessão). Nada de código antes do plano aprovado.
- **Este computador** (clone novo, 03/10/2026): faltam uv, Python 3.14 (via uv) e PostgreSQL 18. O plugin superpowers já está instalado (`superpowers@anthropic-plugin-directory`, versão 6.4.2).

## Onde está cada coisa

- `docs/superpowers/specs/`: especificação. A seção 13 registra todas as decisões e de onde vieram.
- `docs/superpowers/plans/`: plano de implementação, em etapas e tarefas com testes.
- `docs/esbocos/`: esboços aprovados (abrem no navegador).
  - `identidade-visual-v3.html`: identidade e tela de novo pedido (interativa).
  - `telas.html`: demais telas.
  - `relatorios.html`: relatórios.
- `docs/assets/logo-helptoner.png`: logo oficial (usar este PNG, não o SVG antigo).

## Convenções

- Conversar com Lucas em **português do Brasil**, em linguagem simples e direta.
- Stack: Django 6.1 + HTMX + PostgreSQL 18 (Neon, São Paulo, conta própria) + Vercel Hobby, todos em planos gratuitos. Plano B: Render. Detalhes na seção 5 da especificação.
- **Custo zero:** todo serviço precisa ser gratuito (pedido de Lucas). A Vercel Hobby é uma exceção consciente aos termos de uso comercial (decisão 20); para qualquer serviço novo, escolher planos gratuitos que permitam uso comercial e conferir os termos antes de propor.
- Git deste projeto: perfil **pessoal** (`lucastonnon` / `lucastonnon@gmail.com`), configurado só neste repositório. Não usar a identidade global (é a profissional). Repositório: `github.com/tonnon/helptoner-admin` (privado).
- Commits **sem** linha `Co-Authored-By` do Claude nem qualquer menção ao Claude como autor ou coautor (pedido de Lucas).
- Seguir o fluxo superpowers: especificação → plano → implementação com TDD.
