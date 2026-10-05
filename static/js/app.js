// JavaScript próprio do sistema: diálogos, menu do celular e avisos.
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
  document.addEventListener("htmx:responseError", () => mostrarAviso(ERRO_PADRAO, "erro"));
  document.addEventListener("htmx:sendError", () => mostrarAviso(ERRO_PADRAO, "erro"));

  // Avisos que já vieram na página (mensagens do Django).
  document.querySelectorAll("#avisos .toast").forEach(agendarSaida);
})();
