// Busca com sugestões do editor do pedido (cliente e produto), como no esboço
// docs/esbocos/identidade-visual-v3.html. O servidor manda as opções prontas pelo HTMX; aqui ficam
// só o teclado, a escolha e abrir/fechar a lista. Sem HTML em texto, por causa da CSP.
//
// Cada [data-sugestoes] tem um campo [data-sugestoes-campo] (role=combobox) e uma lista
// [role=listbox]. Quando os resultados chegam, a primeira opção disponível já fica selecionada;
// as setas movem a seleção, Enter escolhe, Esc fecha e a lista fecha 120 ms depois de o campo
// perder o foco.
// - Opção de cliente: um botão com hx-post (escolher = clicar nele).
// - Opção de produto: preenche o campo escondido (data-sugestoes-escolhido), o texto do campo e a
//   linha de informação (data-sugestoes-info) e põe o foco na quantidade (data-sugestoes-foco).
(() => {
  "use strict";

  const ESPERA_AO_SAIR = 120;
  const DISPONIVEIS = '[role="option"]:not([aria-disabled="true"])';

  const caixaDe = (elemento) => elemento.closest("[data-sugestoes]");
  const campoDe = (caixa) => caixa.querySelector("[data-sugestoes-campo]");
  const listaDe = (caixa) => caixa.querySelector('[role="listbox"]');
  const disponiveis = (caixa) => [...listaDe(caixa).querySelectorAll(DISPONIVEIS)];
  const selecionada = (caixa) => listaDe(caixa).querySelector('[aria-selected="true"]');
  const aberta = (caixa) => caixa.classList.contains("aberta");
  const porId = (id) => (id ? document.getElementById(id) : null);
  // Produto já escolhido: voltar ao campo não reabre a lista (digitar desfaz a escolha).
  const temEscolha = (caixa) => Boolean(porId(caixa.dataset.sugestoesEscolhido)?.value);

  function campoDaSugestao(alvo) {
    return alvo instanceof Element ? alvo.closest("[data-sugestoes-campo]") : null;
  }

  function abrir(caixa) {
    caixa.classList.add("aberta");
    campoDe(caixa).setAttribute("aria-expanded", "true");
  }

  function fechar(caixa) {
    caixa.classList.remove("aberta");
    const campo = campoDe(caixa);
    campo.setAttribute("aria-expanded", "false");
    campo.removeAttribute("aria-activedescendant");
  }

  function selecionar(caixa, opcao) {
    listaDe(caixa)
      .querySelectorAll('[role="option"]')
      .forEach((cada) => cada.setAttribute("aria-selected", String(cada === opcao)));
    const campo = campoDe(caixa);
    if (opcao) {
      campo.setAttribute("aria-activedescendant", opcao.id);
      opcao.scrollIntoView({ block: "nearest" });
    } else {
      campo.removeAttribute("aria-activedescendant");
    }
  }

  // Setas: a seleção anda entre as opções disponíveis e para na primeira e na última.
  function mover(caixa, passo) {
    const opcoes = disponiveis(caixa);
    if (!opcoes.length) return;
    const atual = opcoes.indexOf(selecionada(caixa));
    const proxima = atual < 0 ? 0 : Math.min(opcoes.length - 1, Math.max(0, atual + passo));
    selecionar(caixa, opcoes[proxima]);
  }

  // "R$ 189,90 cada · 12 em estoque · 3 já no pedido"
  function mostrarInfo(info, opcao) {
    if (!info) return;
    info.replaceChildren();
    if (!opcao) return;
    const preco = document.createElement("b");
    preco.textContent = opcao.dataset.preco;
    const estoque = document.createElement("b");
    estoque.textContent = opcao.dataset.estoque;
    info.append(preco, " cada · ", estoque, " em estoque");
    if (opcao.dataset.noPedido && opcao.dataset.noPedido !== "0") {
      info.append(` · ${opcao.dataset.noPedido} já no pedido`);
    }
  }

  function escolherProduto(caixa, opcao) {
    const escolhido = porId(caixa.dataset.sugestoesEscolhido);
    if (escolhido) escolhido.value = opcao.dataset.produtoId;
    campoDe(caixa).value = opcao.dataset.texto;
    mostrarInfo(porId(caixa.dataset.sugestoesInfo), opcao);
    const foco = porId(caixa.dataset.sugestoesFoco);
    if (foco) {
      foco.focus();
      foco.select();
    }
  }

  // Clicar na lista não tira o foco do campo (senão ela fecharia antes do clique).
  document.addEventListener("mousedown", (evento) => {
    if (evento.target instanceof Element && evento.target.closest("[data-sugestoes] .sugestoes")) {
      evento.preventDefault();
    }
  });

  document.addEventListener("click", (evento) => {
    if (!(evento.target instanceof Element)) return;
    // "Trocar" o cliente: mostra a busca de novo, com o foco nela.
    const trocar = evento.target.closest("[data-trocar-cliente]");
    if (trocar) {
      const bloco = trocar.closest("[data-cliente]");
      const caixa = bloco.querySelector("[data-sugestoes]");
      bloco.querySelector("[data-cliente-escolhido]").hidden = true;
      caixa.hidden = false;
      campoDe(caixa).focus();
      return;
    }
    // Escolher uma opção. O botão do cliente faz o próprio hx-post (o HTMX cuida do clique).
    const opcao = evento.target.closest('[data-sugestoes] [role="option"]');
    if (!opcao || opcao.getAttribute("aria-disabled") === "true") return;
    const caixa = caixaDe(opcao);
    fechar(caixa);
    if (opcao.dataset.produtoId) escolherProduto(caixa, opcao);
  });

  document.addEventListener("keydown", (evento) => {
    const campo = campoDaSugestao(evento.target);
    if (!campo) return;
    const caixa = caixaDe(campo);
    const buscando = caixa.classList.contains("htmx-request"); // as opções na lista são as antigas
    if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
      if (buscando || !disponiveis(caixa).length) return;
      evento.preventDefault();
      if (!aberta(caixa)) {
        abrir(caixa); // reabre com a seleção que já havia
        if (!selecionada(caixa)) mover(caixa, 1);
      } else {
        mover(caixa, evento.key === "ArrowDown" ? 1 : -1);
      }
    } else if (evento.key === "Enter" && aberta(caixa)) {
      evento.preventDefault(); // não envia o formulário do item
      const opcao = buscando ? null : selecionada(caixa);
      if (opcao && opcao.getAttribute("aria-disabled") !== "true") opcao.click();
    } else if (evento.key === "Escape" && aberta(caixa)) {
      evento.preventDefault();
      fechar(caixa);
    }
  });

  // Digitar de novo desfaz a escolha do produto (o campo escondido e a linha de informação).
  document.addEventListener("input", (evento) => {
    const campo = campoDaSugestao(evento.target);
    if (!campo) return;
    const caixa = caixaDe(campo);
    const escolhido = porId(caixa.dataset.sugestoesEscolhido);
    if (escolhido) escolhido.value = "";
    mostrarInfo(porId(caixa.dataset.sugestoesInfo), null);
  });

  document.addEventListener("focusout", (evento) => {
    const campo = campoDaSugestao(evento.target);
    if (!campo) return;
    const caixa = caixaDe(campo);
    setTimeout(() => {
      if (document.activeElement !== campo) fechar(caixa);
    }, ESPERA_AO_SAIR);
  });

  // A busca começou: a lista abre com o esqueleto (o HTMX põe .htmx-request na caixa).
  document.addEventListener("htmx:beforeRequest", (evento) => {
    const campo = campoDaSugestao(evento.detail.elt);
    if (!campo || !campo.value.trim() || document.activeElement !== campo) return;
    const caixa = caixaDe(campo);
    if (!temEscolha(caixa)) abrir(caixa);
  });

  // Os resultados chegaram: a primeira opção disponível já fica selecionada.
  document.addEventListener("htmx:afterSwap", (evento) => {
    const lista = evento.target;
    if (!(lista instanceof Element) || !lista.matches('[data-sugestoes] [role="listbox"]')) return;
    const caixa = caixaDe(lista);
    if (!lista.children.length || document.activeElement !== campoDe(caixa) || temEscolha(caixa)) {
      fechar(caixa);
      return;
    }
    // Liga já o hx-post das opções (o HTMX faria isso só no fim da troca), para um Enter logo
    // depois de os resultados chegarem também escolher o cliente.
    window.htmx?.process(lista);
    abrir(caixa);
    selecionar(caixa, disponiveis(caixa)[0] || null);
  });
})();
