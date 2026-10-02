# Helptoner Pedidos

Sistema web de pedidos de venda da Helptoner (empresa familiar de toners). Substitui o app desktop antigo (`app.py`, Tkinter + SQLite), que tinha bugs de estoque, desconto e numeração.

## Estado atual (02/10/2026)

- **Design aprovado** em 5 partes: regras de negócio, usuários e segurança, arquitetura, telas, operação.
- **Especificação escrita**: `docs/superpowers/specs/2026-10-02-helptoner-pedidos-design.md`. Aguarda a revisão final de Lucas, com três pontos a confirmar (decisões 18 e 19 na seção 13, e a publicação manual pelo botão "Publicar", que prevalece sobre a Parte 3).
- **Próximo passo:** depois da aprovação da especificação, criar o plano de implementação (skill `superpowers:writing-plans`), dividido em etapas que entregam algo funcionando e testado. Nada de código antes do plano aprovado.

## Onde está cada coisa

- `docs/superpowers/specs/`: especificação. A seção 13 registra todas as decisões e de onde vieram.
- `docs/esbocos/`: esboços aprovados (abrem no navegador).
  - `identidade-visual-v3.html`: identidade e tela de novo pedido (interativa).
  - `telas.html`: demais telas.
  - `relatorios.html`: relatórios.
- `docs/assets/logo-helptoner.png`: logo oficial (usar este PNG, não o SVG antigo).

## Convenções

- Conversar com Lucas em **português do Brasil**, em linguagem simples e direta.
- Stack: Django 6.1 + HTMX + PostgreSQL 18 (Neon, São Paulo) + Vercel Pro. Detalhes na seção 5 da especificação.
- Git deste projeto: perfil **pessoal** (`lucastonnon` / `lucastonnon@gmail.com`), configurado só neste repositório. Não usar a identidade global (é a profissional). Repositório: `github.com/tonnon/helptoner-admin` (privado).
- Commits **sem** linha `Co-Authored-By` do Claude nem qualquer menção ao Claude como autor ou coautor (pedido de Lucas).
- Seguir o fluxo superpowers: especificação → plano → implementação com TDD.
