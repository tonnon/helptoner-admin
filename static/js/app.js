// JavaScript próprio do sistema: diálogos, menu do celular, avisos e animação de valores.
// Respeita a CSP: nada de HTML em texto; só classes, textContent e elementos clonados.
(() => {
  "use strict";

  const DURACAO_AVISO = 3200;
  const DURACAO_SAIDA = 300;
  const ERRO_PADRAO = "Não foi possível concluir. Tente de novo.";

  function agendarSaida(aviso) {
    setTimeout(() => {
      aviso.classList.add("saindo");
      setTimeout(() => aviso.remove(), DURACAO_SAIDA);
    }, DURACAO_AVISO);
  }

  function mostrarAviso(texto, tipo) {
    const modelo = document.getElementById("modelo-aviso");
    const lista = document.getElementById("avisos");
    if (!modelo || !lista) return;
    const aviso = modelo.content.firstElementChild.cloneNode(true);
    aviso.querySelector("[data-texto]").textContent = texto;
    aviso.classList.toggle("toast-erro", tipo === "erro");
    lista.append(aviso);
    agendarSaida(aviso);
  }

  document.addEventListener("click", (evento) => {
    const abrir = evento.target.closest("[data-abrir-dialogo]");
    if (abrir) {
      const dialogo = document.getElementById(abrir.dataset.abrirDialogo);
      if (dialogo && !dialogo.open) dialogo.showModal();
      return;
    }
    const fechar = evento.target.closest("[data-fechar-dialogo]");
    if (fechar) {
      fechar.closest("dialog")?.close();
      return;
    }
    const alternar = evento.target.closest("[data-alternar-menu]");
    if (alternar) {
      const menu = document.getElementById(alternar.getAttribute("aria-controls"));
      if (!menu) return;
      const aberto = menu.classList.toggle("aberto");
      alternar.setAttribute("aria-expanded", String(aberto));
    }
  });

  // HX-Trigger: {"aviso": {"texto": "...", "tipo": "sucesso" | "erro"}} (apps.core.htmx.avisar)
  document.addEventListener("aviso", (evento) => {
    const { texto, tipo } = evento.detail || {};
    if (texto) mostrarAviso(texto, tipo);
  });
  // HX-Trigger-After-Settle: {"focar": "<id>"} põe o foco no campo, se a troca o deixou sem dono
  // (no <body>). Se a pessoa já foi para outro campo, o foco fica onde ela está.
  document.addEventListener("focar", (evento) => {
    const campo = document.getElementById(evento.detail?.value);
    if (campo && (!document.activeElement || document.activeElement === document.body)) {
      campo.focus();
    }
  });

  document.addEventListener("htmx:responseError", () => mostrarAviso(ERRO_PADRAO, "erro"));
  document.addEventListener("htmx:sendError", () => mostrarAviso(ERRO_PADRAO, "erro"));

  // Valores que contam até o novo (ex.: o total do pedido). Quando uma resposta troca um elemento
  // [data-valor-centavos] com id, ele vai do valor que estava na tela até o novo em 520 ms e
  // termina com o texto que veio do servidor. Com "reduzir movimento", o valor só troca.
  const DURACAO_CONTAGEM = 520;
  const reduzirMovimento = window.matchMedia("(prefers-reduced-motion: reduce)");
  const contagens = new Map(); // id → { el, valor (centavos na tela), quadro } em andamento
  let antesDaTroca = null; // id → { el, valor }, lido logo antes de cada troca

  // 123456 → "R$ 1.234,56", como o filtro brl do servidor.
  function reais(centavos) {
    const absoluto = Math.abs(Math.round(centavos));
    const inteiro = String(Math.floor(absoluto / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const sinal = centavos < 0 ? "-" : "";
    return `${sinal}R$ ${inteiro},${String(absoluto % 100).padStart(2, "0")}`;
  }

  function valoresNaTela() {
    const valores = new Map();
    document.querySelectorAll("[data-valor-centavos][id]").forEach((el) => {
      const contagem = contagens.get(el.id);
      const valor = contagem?.el === el ? contagem.valor : Number(el.dataset.valorCentavos);
      valores.set(el.id, { el, valor });
    });
    return valores;
  }

  function contar(el, de, ate) {
    const final = el.textContent; // o elemento acabou de chegar do servidor
    const inicio = performance.now();
    cancelAnimationFrame(contagens.get(el.id)?.quadro);
    const contagem = { el, valor: de, quadro: 0 };
    contagens.set(el.id, contagem);
    el.textContent = reais(de); // antes da pintura: o valor novo não pisca antes da contagem
    const passo = (agora) => {
      // O horário do quadro pode vir um pouco antes de `inicio`.
      const progresso = Math.min(1, Math.max(0, (agora - inicio) / DURACAO_CONTAGEM));
      if (progresso < 1) {
        contagem.valor = de + (ate - de) * (1 - Math.pow(1 - progresso, 3));
        el.textContent = reais(contagem.valor);
        contagem.quadro = requestAnimationFrame(passo);
      } else {
        el.textContent = final;
        if (contagens.get(el.id) === contagem) contagens.delete(el.id);
      }
    };
    contagem.quadro = requestAnimationFrame(passo);
  }

  document.addEventListener("htmx:beforeSwap", (evento) => {
    antesDaTroca = valoresNaTela();
    // A linha removida sai animada enquanto a troca espera (hx-swap="... swap:280ms").
    const botao = evento.detail.requestConfig?.elt;
    if (evento.detail.shouldSwap && botao?.matches?.("[data-remover-linha]")) {
      botao.closest("tr")?.classList.add("saindo");
    }
  });

  // Logo depois da troca (todas as partes, inclusive as hx-swap-oob, já estão na página).
  document.addEventListener("htmx:afterSwap", () => {
    const antes = antesDaTroca;
    antesDaTroca = null; // o afterSwap vem uma vez por elemento trocado
    if (!antes || reduzirMovimento.matches) return;
    document.querySelectorAll("[data-valor-centavos][id]").forEach((el) => {
      const anterior = antes.get(el.id);
      if (!anterior || anterior.el === el) return; // não foi trocado por esta resposta
      const ate = Number(el.dataset.valorCentavos);
      if (anterior.valor !== ate) contar(el, anterior.valor, ate);
    });
  });

  // Botões com data-espera-mudancas (o "Confirmar" do pedido) esperam as mudanças que ainda estão
  // a caminho do servidor, como o desconto enviado quando o campo perde o foco no próprio clique:
  // assim o pedido é conferido já com elas.
  const mudancasPendentes = new Set();
  const depoisDasMudancas = [];

  document.addEventListener("htmx:beforeSend", (evento) => {
    const { xhr, requestConfig } = evento.detail;
    if (requestConfig.verb === "get") return;
    mudancasPendentes.add(xhr);
    xhr.addEventListener("loadend", () => {
      mudancasPendentes.delete(xhr);
      if (!mudancasPendentes.size) depoisDasMudancas.splice(0).forEach((funcao) => funcao());
    });
  });

  document.addEventListener("htmx:confirm", (evento) => {
    const botao = evento.detail.elt;
    if (!mudancasPendentes.size || !botao.matches?.("[data-espera-mudancas]")) return;
    evento.preventDefault();
    if (botao.disabled) return; // já está esperando
    botao.disabled = true;
    botao.classList.add("htmx-request");
    depoisDasMudancas.push(() => {
      botao.disabled = false;
      botao.classList.remove("htmx-request");
      // A resposta pode ter redesenhado o botão (a barra do celular): clica no que está na tela.
      (botao.isConnected ? botao : document.getElementById(botao.id))?.click();
    });
  });

  // Avisos que já vieram na página (mensagens do Django).
  document.querySelectorAll("#avisos .toast").forEach(agendarSaida);
})();
