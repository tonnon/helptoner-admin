// Máscaras dos campos (data-mascara="cpf|cnpj|cep|telefone"). Só formatam o que se vê: o
// servidor tira a máscara e confere os dígitos. Sem HTML em texto, por causa da CSP.
(() => {
  "use strict";

  const soDigitos = (texto) => texto.replace(/\D/g, "");
  const soAlfanumericos = (texto) => texto.replace(/[^0-9A-Za-z]/g, "").toUpperCase();

  function cpf(texto) {
    const d = soDigitos(texto).slice(0, 11);
    let saida = d.slice(0, 3);
    if (d.length > 3) saida += "." + d.slice(3, 6);
    if (d.length > 6) saida += "." + d.slice(6, 9);
    if (d.length > 9) saida += "-" + d.slice(9);
    return saida;
  }

  // O CNPJ aceita letras nas 12 primeiras posições; as 2 últimas são dígitos.
  function cnpj(texto) {
    const a = soAlfanumericos(texto).slice(0, 14);
    let saida = a.slice(0, 2);
    if (a.length > 2) saida += "." + a.slice(2, 5);
    if (a.length > 5) saida += "." + a.slice(5, 8);
    if (a.length > 8) saida += "/" + a.slice(8, 12);
    if (a.length > 12) saida += "-" + a.slice(12);
    return saida;
  }

  function cep(texto) {
    const d = soDigitos(texto).slice(0, 8);
    return d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d;
  }

  function telefone(texto) {
    const d = soDigitos(texto).slice(0, 11);
    if (d.length === 0) return "";
    if (d.length <= 2) return "(" + d;
    const miolo = d.length > 10 ? 7 : 6;
    let saida = "(" + d.slice(0, 2) + ") " + d.slice(2, miolo);
    if (d.length > miolo) saida += "-" + d.slice(miolo);
    return saida;
  }

  const MASCARAS = { cpf, cnpj, cep, telefone };

  // O documento segue o tipo escolhido (Pessoa = CPF, Empresa = CNPJ).
  function mascaraDe(campo) {
    const nome = campo.dataset.mascara;
    if (nome !== "cnpj" && nome !== "cpf") return MASCARAS[nome];
    const escolhido = campo.form && campo.form.querySelector('input[name="tipo"]:checked');
    return escolhido && escolhido.value === "PF" ? cpf : cnpj;
  }

  function aplicar(campo) {
    const mascara = mascaraDe(campo);
    if (mascara) campo.value = mascara(campo.value);
  }

  document.addEventListener("input", (evento) => {
    const campo = evento.target.closest("[data-mascara]");
    if (campo) aplicar(campo);
  });

  document.addEventListener("change", (evento) => {
    if (evento.target.name === "tipo" && evento.target.form) {
      evento.target.form.querySelectorAll("[data-mascara]").forEach(aplicar);
    }
  });

  document.querySelectorAll("[data-mascara]").forEach(aplicar);
})();
