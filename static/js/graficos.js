// Gráficos dos relatórios em SVG, adaptados de docs/esbocos/relatorios.html. Regras da §7: as cores
// das séries vêm do servidor (#0200FF e #eb6834), uma escala só por gráfico, linhas de 2 px, barras
// de 18 px (no máximo 24) com a ponta arredondada, rótulos diretos só nos pontos finais e mira
// vertical com caixa de valores pelo mouse e pelas setas do teclado.
// Os dados chegam em <script type="application/json"> (json_script do Django), com os valores em
// texto decimal e os textos já formatados pelo servidor. A tabela de cada gráfico também vem do
// servidor; a chave "Gráfico | Tabela" só alterna o atributo hidden.
// Respeita a CSP: nada de HTML em texto nem de atributo style; só elementos, classes, textContent
// e elemento.style (CSSOM) para posicionar a caixa de valores.
(() => {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const ESPERA_REDIMENSIONAR = 150; // ms sem mudar de tamanho antes de redesenhar
  const ESTREITO = 520; // px: abaixo disso, margens menores e textos curtos
  const ALTURA_LINHAS = 300;
  const FAIXA_BARRA = 40; // altura reservada para cada produto
  const ESPESSURA_BARRA = 18; // §7: no máximo 24 px
  const PONTA = 4; // raio da ponta arredondada da barra (a base fica reta)
  const DISTANCIA_ROTULOS = 30; // espaço vertical de um rótulo final (valor + nome)

  const umaCasa = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  // Área do gráfico → interação do desenho atual (redesenhar troca o estado, não os ouvintes).
  const estados = new WeakMap();

  function svg(tag, atributos, pai) {
    const el = document.createElementNS(NS, tag);
    for (const [nome, valor] of Object.entries(atributos)) el.setAttribute(nome, valor);
    pai.appendChild(el);
    return el;
  }

  function escrever(pai, atributos, conteudo) {
    svg("text", atributos, pai).textContent = conteudo;
  }

  function elemento(tag, classe, conteudo) {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (conteudo !== undefined) el.textContent = conteudo;
    return el;
  }

  // 41230.9 → "R$ 41,2 mil"; 1250000 → "R$ 1,3 mi"; 500 → "R$ 500". Sem o "R$" se `curto`.
  function compacto(valor, curto = false) {
    const absoluto = Math.abs(valor);
    let numero = umaCasa.format(absoluto);
    if (absoluto >= 1e6) numero = `${umaCasa.format(absoluto / 1e6)} mi`;
    else if (absoluto >= 1e3) numero = `${umaCasa.format(absoluto / 1e3)} mil`;
    const resultado = curto ? numero : `R$ ${numero}`;
    return valor < 0 ? `-${resultado}` : resultado;
  }

  // O valor ao lado da marca: o texto exato do servidor até R$ 999,99; daí para cima, compacto.
  function rotuloDoValor(valor, textoExato) {
    return Math.abs(valor) >= 1000 ? compacto(valor) : textoExato;
  }

  // Escala "redonda" que sempre inclui o zero, com uns 5 intervalos (0, 10 mil, 20 mil…).
  function escala(minimo, maximo) {
    let inferior = Math.min(0, minimo);
    let superior = Math.max(0, maximo);
    if (superior === inferior) superior = 100; // tudo zero: qualquer escala serve
    const bruto = (superior - inferior) / 5;
    const potencia = 10 ** Math.floor(Math.log10(bruto));
    const passo = [1, 2, 2.5, 5, 10].map((m) => m * potencia).find((p) => p >= bruto * 0.999);
    inferior = Math.floor(inferior / passo) * passo;
    superior = Math.ceil(superior / passo) * passo;
    const intervalos = Math.round((superior - inferior) / passo);
    const marcas = Array.from({ length: intervalos + 1 }, (_, i) => inferior + i * passo);
    return { inferior, superior, marcas };
  }

  function limitar(indice, ultimo) {
    return Math.max(0, Math.min(ultimo, indice));
  }

  // Setas (→ ↓ avançam, ← ↑ voltam), Home e End. Devolve o novo índice ou null.
  function indiceDaTecla(evento, atual, ultimo) {
    const destinos = {
      ArrowRight: atual + 1,
      ArrowDown: atual + 1,
      ArrowLeft: atual - 1,
      ArrowUp: atual - 1,
      Home: 0,
      End: ultimo,
    };
    if (!(evento.key in destinos)) return null;
    evento.preventDefault(); // as setas não rolam a página enquanto exploram o gráfico
    return limitar(destinos[evento.key], ultimo);
  }

  // linhas: [{ cor?, valor?, texto }]. O valor vem em destaque; o nome da série, depois.
  function preencherCaixa(caixa, titulo, linhas) {
    const filhos = [elemento("div", "tit", titulo)];
    for (const { cor, valor, texto } of linhas) {
      if (!texto) continue;
      const linha = elemento("div", "lin");
      if (cor) {
        const chave = elemento("i");
        chave.style.backgroundColor = cor; // CSSOM: a CSP permite (atributo style, não)
        linha.append(chave);
      }
      if (valor) linha.append(elemento("b", "", valor));
      linha.append(elemento("span", "", texto));
      filhos.push(linha);
    }
    caixa.replaceChildren(...filhos);
  }

  // Põe a caixa à direita do ponto (xArea, yArea) da área do gráfico, ou à esquerda se não
  // couber no cartão. A caixa e a área ficam dentro do mesmo cartão (position: relative).
  function posicionarCaixa(caixa, area, xArea, yArea) {
    const cartao = caixa.offsetParent;
    const largura = caixa.offsetWidth;
    const x = area.offsetLeft + xArea;
    let esquerda = x + 18;
    if (cartao && esquerda + largura > cartao.clientWidth - 8) esquerda = x - largura - 18;
    caixa.style.left = `${Math.max(8, esquerda)}px`;
    caixa.style.top = `${area.offsetTop + yArea}px`;
    caixa.classList.add("visivel");
  }

  // Os rótulos finais precisam de DISTANCIA_ROTULOS na vertical: se as linhas terminam perto, o de
  // baixo desce (e uma linha-guia liga cada rótulo ao seu ponto). Todos ficam entre `topo` e
  // `fundo`, acima dos rótulos do eixo x.
  function afastarRotulos(fins, topo, fundo) {
    const ordem = [...fins].sort((a, b) => a.yPonto - b.yPonto);
    ordem.forEach((fim, k) => {
      fim.yRotulo = k ? Math.max(fim.yPonto, ordem[k - 1].yRotulo + DISTANCIA_ROTULOS) : fim.yPonto;
    });
    const sobra = ordem.at(-1).yRotulo - fundo;
    if (sobra > 0) ordem.forEach((fim) => (fim.yRotulo -= sobra));
    const falta = topo - ordem[0].yRotulo;
    if (falta > 0) ordem.forEach((fim) => (fim.yRotulo += falta));
  }

  /* ---------- Linhas: faturamento líquido e lucro bruto no tempo (uma escala) ---------- */
  function desenharLinhas(area, dados, caixa) {
    area.replaceChildren();
    const rotulos = dados.rotulos;
    const quantos = rotulos.length;
    if (!quantos) return null;
    const series = dados.series.map((s) => ({ ...s, numeros: s.valores.map(Number) }));
    const largura = area.clientWidth;
    const altura = ALTURA_LINHAS;
    const estreito = largura < ESTREITO;
    const m = { t: 14, r: estreito ? 106 : 132, b: 30, l: estreito ? 54 : 74 };
    const larguraUtil = largura - m.l - m.r;
    const todos = series.flatMap((s) => s.numeros);
    const { inferior, superior, marcas } = escala(Math.min(...todos), Math.max(...todos));
    const passoX = quantos === 1 ? 0 : larguraUtil / (quantos - 1);
    const x = (i) => (quantos === 1 ? m.l + larguraUtil / 2 : m.l + i * passoX);
    const y = (v) => m.t + ((superior - v) / (superior - inferior)) * (altura - m.t - m.b);
    const raiz = svg(
      "svg",
      { width: largura, height: altura, viewBox: `0 0 ${largura} ${altura}`, "aria-hidden": "true" },
      area,
    );

    for (const v of marcas) {
      svg("line", { x1: m.l, x2: largura - m.r, y1: y(v), y2: y(v), class: v === 0 ? "eixo" : "grade" }, raiz);
      const rotulo = v === 0 ? (estreito ? "0" : "R$ 0") : compacto(v, estreito);
      escrever(raiz, { x: m.l - 10, y: y(v) + 4, "text-anchor": "end", class: "tick" }, rotulo);
    }
    // Rótulos do período, contados do último para trás, espaçados para caber (~58 px cada).
    const cada = Math.ceil(quantos / Math.max(2, Math.floor(larguraUtil / 58)));
    rotulos.forEach((rotulo, i) => {
      if ((quantos - 1 - i) % cada === 0) {
        escrever(raiz, { x: x(i), y: altura - 8, "text-anchor": "middle", class: "tick" }, rotulo);
      }
    });

    const caminho = (numeros) =>
      numeros.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const [primeira] = series;
    const base = y(0).toFixed(1);
    svg(
      "path",
      {
        d: `${caminho(primeira.numeros)}L${x(quantos - 1).toFixed(1)},${base}L${x(0).toFixed(1)},${base}Z`,
        fill: primeira.cor,
        "fill-opacity": "0.08",
      },
      raiz,
    );
    for (const s of series) {
      svg(
        "path",
        {
          d: caminho(s.numeros),
          fill: "none",
          stroke: s.cor,
          "stroke-width": 2,
          "stroke-linejoin": "round",
          "stroke-linecap": "round",
        },
        raiz,
      );
    }

    // Pontos finais com anel branco e rótulos diretos só ali.
    const ultimo = quantos - 1;
    const xFim = x(ultimo);
    const fins = series.map((s) => ({ s, yPonto: y(s.numeros[ultimo]) }));
    afastarRotulos(fins, 14, altura - m.b - 4);
    for (const { s, yPonto, yRotulo } of fins) {
      if (Math.abs(yRotulo - yPonto) > 2) {
        svg("line", { x1: xFim + 5, y1: yPonto, x2: xFim + 10, y2: yRotulo - 6, class: "guia" }, raiz);
      }
      svg("circle", { cx: xFim, cy: yPonto, r: 4, fill: s.cor, stroke: "#fff", "stroke-width": 2 }, raiz);
      const valor = rotuloDoValor(s.numeros[ultimo], s.textos[ultimo]);
      escrever(raiz, { x: xFim + 12, y: yRotulo - 2, class: "rotulo-fim" }, valor);
      const nome = estreito ? s.nome.split(" ")[0] : s.nome;
      escrever(raiz, { x: xFim + 12, y: yRotulo + 13, class: "rotulo-fim-sub" }, nome);
    }

    // Mira vertical e marcadores que seguem o mouse ou as setas.
    const mira = svg("line", { y1: m.t, y2: altura - m.b, class: "mira", visibility: "hidden" }, raiz);
    const marcadores = series.map((s) =>
      svg("circle", { r: 5, fill: s.cor, stroke: "#fff", "stroke-width": 2, visibility: "hidden" }, raiz),
    );
    let atual = ultimo;

    function mostrar(i) {
      if (i === atual && caixa.classList.contains("visivel")) return;
      atual = i;
      for (const [nome, valor] of [["x1", x(i)], ["x2", x(i)], ["visibility", "visible"]]) {
        mira.setAttribute(nome, valor);
      }
      marcadores.forEach((marcador, k) => {
        marcador.setAttribute("cx", x(i));
        marcador.setAttribute("cy", y(series[k].numeros[i]));
        marcador.setAttribute("visibility", "visible");
      });
      preencherCaixa(caixa, rotulos[i], [
        ...series.map((s) => ({ cor: s.cor, valor: s.textos[i], texto: s.nome })),
        { texto: dados.detalhes?.[i] },
      ]);
      posicionarCaixa(caixa, area, x(i), 10);
    }

    function esconder() {
      mira.setAttribute("visibility", "hidden");
      marcadores.forEach((marcador) => marcador.setAttribute("visibility", "hidden"));
      caixa.classList.remove("visivel");
    }

    return {
      apontar(evento) {
        const px = evento.clientX - raiz.getBoundingClientRect().left;
        mostrar(passoX ? limitar(Math.round((px - m.l) / passoX), ultimo) : 0);
      },
      focar: () => mostrar(atual),
      esconder,
      tecla(evento) {
        const indice = indiceDaTecla(evento, atual, ultimo);
        if (indice !== null) mostrar(indice);
      },
    };
  }

  /* ---------- Barras horizontais: produtos que mais faturaram (uma série, uma cor) ---------- */
  function desenharBarras(area, dados, caixa) {
    area.replaceChildren();
    const itens = dados.itens.map((item) => ({ ...item, numero: Number(item.valor) }));
    if (!itens.length) return null;
    const largura = area.clientWidth;
    const altura = itens.length * FAIXA_BARRA + 6;
    const inicio = Math.min(170, largura * 0.42); // os códigos ficam à esquerda do eixo
    const folga = 92; // o valor fica depois da ponta da barra
    const maximo = Math.max(...itens.map((item) => item.numero)) || 1;
    const comprimento = (v) => Math.max(0, ((largura - inicio - folga) * v) / maximo);
    const raiz = svg(
      "svg",
      { width: largura, height: altura, viewBox: `0 0 ${largura} ${altura}`, "aria-hidden": "true" },
      area,
    );
    svg("line", { x1: inicio, x2: inicio, y1: 0, y2: altura, class: "eixo" }, raiz);

    const barras = itens.map((item, i) => {
      const meio = i * FAIXA_BARRA + FAIXA_BARRA / 2 + 2;
      const topo = meio - ESPESSURA_BARRA / 2;
      const baixo = meio + ESPESSURA_BARRA / 2;
      const fim = inicio + comprimento(item.numero);
      const r = Math.min(PONTA, fim - inicio);
      escrever(raiz, { x: inicio - 10, y: meio + 4, "text-anchor": "end", class: "rotulo-barra" }, item.codigo);
      // Ponta arredondada (4 px) só na ponta; a base, no eixo, fica reta.
      const barra = svg(
        "path",
        {
          d: `M${inicio},${topo}H${fim - r}Q${fim},${topo} ${fim},${topo + r}V${baixo - r}Q${fim},${baixo} ${fim - r},${baixo}H${inicio}Z`,
          class: "barra",
        },
        raiz,
      );
      escrever(raiz, { x: fim + 8, y: meio + 4, class: "valor-barra" }, rotuloDoValor(item.numero, item.texto));
      return { barra, fim };
    });

    let atual = 0;
    const ultimo = itens.length - 1;

    function mostrar(i) {
      if (i === atual && caixa.classList.contains("visivel")) return;
      atual = i;
      barras.forEach(({ barra }, k) => barra.classList.toggle("apagada", k !== i));
      const item = itens[i];
      preencherCaixa(caixa, `${item.codigo} · ${item.descricao}`, [
        { valor: item.texto, texto: "faturamento líquido" },
        ...item.detalhes.map((detalhe) => ({ texto: detalhe })),
      ]);
      posicionarCaixa(caixa, area, barras[i].fim - 6, (i + 1) * FAIXA_BARRA);
    }

    function esconder() {
      barras.forEach(({ barra }) => barra.classList.remove("apagada"));
      caixa.classList.remove("visivel");
    }

    return {
      apontar(evento) {
        const py = evento.clientY - raiz.getBoundingClientRect().top;
        mostrar(limitar(Math.floor(py / FAIXA_BARRA), ultimo));
      },
      focar: () => mostrar(atual),
      esconder,
      tecla(evento) {
        const indice = indiceDaTecla(evento, atual, ultimo);
        if (indice !== null) mostrar(indice);
      },
    };
  }

  /* ---------- Ligação com a página ---------- */
  function ligar(area) {
    const chamar = (nome) => (evento) => estados.get(area)?.[nome](evento);
    area.addEventListener("pointermove", chamar("apontar"));
    area.addEventListener("pointerleave", chamar("esconder"));
    area.addEventListener("focus", chamar("focar"));
    area.addEventListener("blur", chamar("esconder"));
    area.addEventListener("keydown", chamar("tecla"));
  }

  function desenhar(area) {
    const fonte = document.getElementById(area.dataset.dados);
    const caixa = area.closest("[data-vistas]")?.querySelector("[data-caixa]");
    if (!fonte || !caixa || area.hidden) return;
    caixa.classList.remove("visivel");
    const desenho = area.dataset.grafico === "linha" ? desenharLinhas : desenharBarras;
    if (!estados.has(area)) ligar(area);
    estados.set(area, desenho(area, JSON.parse(fonte.textContent), caixa));
  }

  function desenharTodos() {
    document.querySelectorAll("[data-grafico]").forEach(desenhar);
  }

  // Chave "Gráfico | Tabela": a tabela já veio do servidor; só troca o que fica escondido.
  document.addEventListener("click", (evento) => {
    const botao = evento.target.closest("[data-vistas] [data-vista]");
    if (!botao) return;
    const cartao = botao.closest("[data-vistas]");
    const tabela = botao.dataset.vista === "tabela";
    cartao.querySelectorAll("[data-vista]").forEach((b) => b.setAttribute("aria-pressed", String(b === botao)));
    const area = cartao.querySelector("[data-grafico]");
    area.hidden = tabela;
    cartao.querySelector("[data-vista-tabela]").hidden = !tabela;
    cartao.querySelector("[data-caixa]")?.classList.remove("visivel");
    if (!tabela) desenhar(area); // a largura pode ter mudado enquanto estava escondido
  });

  // O HTMX trocou o conteúdo do relatório (primeira carga ou filtro novo).
  document.addEventListener("htmx:afterSwap", (evento) => {
    if (evento.detail.target?.id === "relatorio") desenharTodos();
  });

  let espera;
  window.addEventListener("resize", () => {
    clearTimeout(espera);
    espera = setTimeout(desenharTodos, ESPERA_REDIMENSIONAR);
  });

  desenharTodos();
})();
