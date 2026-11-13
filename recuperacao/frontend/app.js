// Questionário do aluno: escolhe temas do catálogo e/ou escreve um texto livre,
// envia para POST /recomendar e mostra os professores recomendados, com a explicação
// de por que cada um apareceu e a opção de comparar até 3 lado a lado.
//
// Endereço da API:
//   - servido pela própria API (/app/): mesmo endereço, nada a configurar;
//   - aberto de outro lugar: ?api=https://xxxx.trycloudflare.com na URL;
//   - aberto como arquivo (file://): http://localhost:8000.
//
// TODO(api): dados que enriqueceriam a interface e hoje não vêm de POST /recomendar:
//   - "ano" de cada item em "destaques" (mostrar a recência das evidências e ordenar por ano);
//   - link do Lattes, e-mail ou página do professor (botão "Entrar em contato");
//   - área/departamento e foto do professor (avatar no cartão);
//   - progresso real da busca (SSE/streaming por etapa) no lugar das etapas estimadas por tempo;
//   - total de evidências por tipo, não só os top n_itens, para "3 de 12 produções".
(() => {
  "use strict";

  const MAX_TEMAS = 3;
  const MAX_COMPARAR = 3;
  const N_ITENS = 3;
  const NOME_TEXTO_LIVRE = "Texto livre";
  const TODAS = "Todas";

  const ROTULO_TIPO = {
    producao: "Produções",
    projeto: "Projetos",
    orientacao: "Orientações",
    trabalho: "Iniciação científica",
    disciplina: "Disciplinas",
  };
  const CONTAGEM_TIPO = {
    producao: ["produção", "produções"],
    projeto: ["projeto", "projetos"],
    orientacao: ["orientação", "orientações"],
    trabalho: ["IC", "ICs"],
    disciplina: ["disciplina", "disciplinas"],
  };
  const ORDEM_TIPOS = ["producao", "projeto", "orientacao", "trabalho", "disciplina"];
  const ROTULO_SUBTIPO = {
    livro: "Livro",
    artigo_periodico: "Artigo em periódico",
    capitulo_livro: "Capítulo de livro",
    trabalho_congresso: "Trabalho em congresso",
    resumo_expandido: "Resumo expandido",
    pesquisa: "Projeto de pesquisa",
    extensao: "Projeto de extensão",
    desenvolvimento: "Projeto de desenvolvimento",
  };
  // etapas exibidas durante a busca (estimadas por tempo; ver TODO(api))
  const ETAPAS = [
    [0, "Interpretando sua busca…"],
    [1500, "Buscando em produções, projetos, orientações e ICs…"],
    [5000, "Reordenando as evidências com o reranker…"],
    [15000, "Quase lá: a primeira busca de um tema demora mais…"],
  ];

  const API = (() => {
    const param = new URLSearchParams(location.search).get("api");
    if (param) return param.replace(/\/+$/, "");
    if (location.protocol === "file:") return "http://localhost:8000";
    return "";
  })();

  const reduzirMovimento = matchMedia("(prefers-reduced-motion: reduce)");
  const telaLarga = matchMedia("(min-width: 1080px)");

  const $ = (id) => document.getElementById(id);
  const form = $("questionario");
  const areaTemas = $("temas");
  const areaCategorias = $("categorias");
  const campoFiltro = $("filtro");
  const bandeja = $("bandeja");
  const listaSelecionados = $("selecionados");
  const contadorTemas = $("contador-temas");
  const previa = $("previa-tema");
  const avisoTemas = $("aviso-temas");
  const campoTexto = $("texto");
  const contadorTexto = $("contador-texto");
  const campoAno = $("ano-min");
  const resumoOpcoes = $("resumo-opcoes");
  const erroForm = $("erro-formulario");
  const resumoPedido = $("resumo-pedido");
  const botao = $("buscar");
  const status = $("status");
  const statusEtapa = $("status-etapa");
  const cronometro = $("cronometro");
  const resultado = $("resultado");
  const tituloResultado = $("titulo-resultado");
  const metaResultado = $("meta-resultado");
  const resumoBusca = $("resumo-busca");
  const lista = $("lista-professores");
  const notaCortados = $("nota-cortados");
  const botaoAlternarTodos = $("alternar-todos");
  const barraComparar = $("barra-comparar");
  const textoComparar = $("barra-comparar-texto");
  const botaoComparar = $("abrir-comparacao");
  const dialogo = $("dialogo-comparar");
  const tabelaComparar = $("tabela-comparar");

  /** nome do tema -> slot de cor (0, 1, 2), na ordem de escolha */
  const selecionados = new Map();
  let detalhesTemas = [];
  let categoriaAtual = TODAS;
  let ocupado = false;
  let controlador = null;
  let atual = null;            // { dados, pedido, ctx } da última busca exibida
  const comparados = new Set(); // índices (no ranking atual) marcados para comparar

  $("limite-temas").textContent = String(MAX_TEMAS);

  // ================================================================ utilitários
  // Cria um elemento; textos sempre por textContent (nada da base vira HTML).
  function el(tag, attrs = {}, ...filhos) {
    const no = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") no.className = v;
      else if (k === "texto") no.textContent = v;
      else no.setAttribute(k, v === true ? "" : v);
    }
    for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) no.append(f);
    return no;
  }

  const CAMINHOS_ICONE = {
    x: "M6 6l12 12M18 6 6 18",
    check: "M5 12.5l4.5 4.5L19 7.5",
    livro: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5zM4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5",
  };
  function icone(nome) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("class", "icone");
    svg.setAttribute("aria-hidden", "true");
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", CAMINHOS_ICONE[nome]);
    svg.append(p);
    return svg;
  }

  // sem acentos e minúsculas, preservando o comprimento (para destacar o trecho encontrado)
  function normalizar(s) {
    return String(s || "").normalize("NFC").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  // texto com o trecho que casa com a busca dentro de <mark>
  function comDestaque(texto, termo) {
    const original = String(texto).normalize("NFC");
    const i = termo ? normalizar(original).indexOf(termo) : -1;
    if (i < 0 || normalizar(original).length !== original.length) return [document.createTextNode(original)];
    return [
      document.createTextNode(original.slice(0, i)),
      el("mark", { texto: original.slice(i, i + termo.length) }),
      document.createTextNode(original.slice(i + termo.length)),
    ];
  }

  // aplica a mudança de DOM com View Transition quando disponível; resolve quando o DOM já mudou
  function transicao(atualizar) {
    if (document.startViewTransition && !reduzirMovimento.matches && document.visibilityState === "visible") {
      return document.startViewTransition(atualizar).updateCallbackDone.catch(() => {});
    }
    atualizar();
    return Promise.resolve();
  }

  function plural(n, [um, varios]) { return `${n} ${n === 1 ? um : varios}`; }

  function listaHumana(itens) {
    if (itens.length <= 1) return itens.join("");
    return `${itens.slice(0, -1).join(", ")} e ${itens[itens.length - 1]}`;
  }

  // "CARLOS HENRIQUE DE MORAES" -> "Carlos Henrique de Moraes"
  function tituloNome(nome) {
    const minusculas = new Set(["de", "da", "do", "das", "dos", "e", "em", "para", "a", "o"]);
    const s = String(nome || "");
    if (s !== s.toUpperCase()) return s;
    return s.toLowerCase().split(/\s+/).map((p, i) => {
      if (/^(i{1,3}|iv|v|vi{1,3}|ix|x)$/.test(p)) return p.toUpperCase();   // Circuitos Digitais II
      if (i > 0 && minusculas.has(p)) return p;
      return p.charAt(0).toUpperCase() + p.slice(1);
    }).join(" ");
  }

  function primeiraMaiuscula(texto) {
    const s = String(texto);
    return s === s.toUpperCase() ? tituloNome(s) : s.charAt(0).toUpperCase() + s.slice(1);
  }

  function nomeTopico(t) { return t === NOME_TEXTO_LIVRE ? "Seu texto" : t; }

  // ================================================================ tema claro/escuro
  (() => {
    const botaoTema = $("alternar-tema");
    const rotulo = $("rotulo-tema");
    const modos = ["auto", "light", "dark"];
    const nomes = { auto: "Automático", light: "Claro", dark: "Escuro" };
    let modo = document.documentElement.dataset.theme || "auto";
    function aplicar() {
      if (modo === "auto") delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = modo;
      rotulo.textContent = nomes[modo];
      botaoTema.setAttribute("aria-label", `Tema: ${nomes[modo].toLowerCase()}. Clique para alternar.`);
      try { modo === "auto" ? localStorage.removeItem("tema") : localStorage.setItem("tema", modo); } catch (e) { /* sem storage */ }
    }
    botaoTema.addEventListener("click", () => {
      // sem View Transition aqui: durante a transição o clique seguinte seria ignorado
      modo = modos[(modos.indexOf(modo) + 1) % modos.length];
      aplicar();
    });
    aplicar();
  })();

  // ================================================================ temas
  async function carregarTemas() {
    try {
      const resp = await fetch(`${API}/topicos`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const dados = await resp.json();
      detalhesTemas = (dados.detalhes || (dados.topicos || []).map((nome) => ({ nome, categoria: "Temas" })))
        .map((t, i) => ({
          ...t,
          id: `tema-${i}`,
          categoria: t.categoria || "Outros",
          disciplinas: (t.disciplinas || []).map(tituloNome),
          indice: {
            nome: normalizar(t.nome),
            disciplinas: (t.disciplinas || []).map((d) => normalizar(d)),
            resto: normalizar(`${t.descricao || ""} ${t.categoria || ""}`),
          },
        }));
      desenharTemas();
    } catch (e) {
      areaTemas.replaceChildren(el("p", {
        class: "erro",
        texto: "Não foi possível carregar os temas. Confira se a API está no ar" +
          (API ? ` (${API})` : "") + ". Você ainda pode buscar pelo texto livre.",
      }));
      previa.hidden = true;
      campoFiltro.disabled = true;
    }
  }

  function desenharTemas() {
    const porCategoria = new Map();
    for (const t of detalhesTemas) {
      if (!porCategoria.has(t.categoria)) porCategoria.set(t.categoria, []);
      porCategoria.get(t.categoria).push(t);
    }
    const categorias = [...porCategoria.keys()].sort((a, b) => a.localeCompare(b, "pt-BR"));

    areaCategorias.replaceChildren(...[TODAS, ...categorias].map((c) => {
      const b = el("button", { type: "button", class: "categoria", "aria-pressed": String(c === categoriaAtual), "data-categoria": c },
        el("span", { texto: c }), el("span", { class: "qtd" }));
      b.addEventListener("click", () => { categoriaAtual = c; filtrar(); });
      return b;
    }));
    if (categorias.length < 2) areaCategorias.hidden = true;

    const grupos = categorias.map((categoria) => el("div", { class: "grupo-temas", "data-categoria": categoria },
      el("h3", { texto: categoria }),
      el("div", { class: "chips" },
        porCategoria.get(categoria)
          .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"))
          .map(criarChip)),
    ));
    const vazio = el("div", { class: "sem-temas", id: "sem-temas", hidden: true });
    const descricoes = el("div", { hidden: true },
      detalhesTemas.map((t) => el("span", { id: `desc-${t.id}`, texto: textoDescricao(t) })));
    areaTemas.replaceChildren(...grupos, vazio, descricoes);
    filtrar();
    atualizarSelecao();
  }

  function textoDescricao(t) {
    const partes = [];
    if (t.descricao) partes.push(primeiraMaiuscula(t.descricao) + ".");
    if (t.disciplinas.length) partes.push(`Disciplinas relacionadas: ${t.disciplinas.join(", ")}.`);
    return partes.join(" ");
  }

  function criarChip(t) {
    const chip = el("button", {
      type: "button", class: "chip-alternar", id: t.id, "aria-pressed": "false",
      "aria-describedby": `desc-${t.id}`, "data-tema": t.nome,
    }, el("span", { class: "chip-nome", texto: t.nome }), el("span", { class: "chip-motivo" }));
    chip.addEventListener("click", () => { alternarTema(t.nome); mostrarPrevia(t); });
    chip.addEventListener("pointerenter", () => mostrarPrevia(t));
    chip.addEventListener("focus", () => mostrarPrevia(t));
    return chip;
  }

  function mostrarPrevia(t) {
    const filhos = [el("p", { class: "previa-nome", texto: t.nome })];
    if (t.descricao) filhos.push(el("p", { texto: primeiraMaiuscula(t.descricao) + "." }));
    if (t.disciplinas.length) filhos.push(el("p", { class: "previa-disciplinas", texto: `Disciplinas: ${t.disciplinas.join(" · ")}` }));
    previa.replaceChildren(...filhos);
  }

  function filtrar() {
    const termo = normalizar(campoFiltro.value.trim());
    const porCategoria = new Map();
    let visiveis = 0;
    for (const t of detalhesTemas) {
      const chip = $(t.id);
      if (!chip) continue;
      let casa = !termo;
      let motivo = "";
      if (termo) {
        if (t.indice.nome.includes(termo)) casa = true;
        else {
          const d = t.indice.disciplinas.findIndex((x) => x.includes(termo));
          if (d >= 0) { casa = true; motivo = `disciplina: ${t.disciplinas[d]}`; }
          else if (t.indice.resto.includes(termo)) { casa = true; motivo = "citado na descrição"; }
        }
      }
      if (casa) porCategoria.set(t.categoria, (porCategoria.get(t.categoria) || 0) + 1);
      const mostrar = casa && (categoriaAtual === TODAS || t.categoria === categoriaAtual);
      chip.hidden = !mostrar;
      if (mostrar) visiveis++;
      chip.querySelector(".chip-nome").replaceChildren(...comDestaque(t.nome, termo));
      chip.querySelector(".chip-motivo").textContent = motivo;
    }
    for (const g of areaTemas.querySelectorAll(".grupo-temas")) {
      g.hidden = !g.querySelector(".chip-alternar:not([hidden])");
    }
    const total = [...porCategoria.values()].reduce((a, b) => a + b, 0);
    for (const b of areaCategorias.querySelectorAll(".categoria")) {
      const c = b.dataset.categoria;
      b.setAttribute("aria-pressed", String(c === categoriaAtual));
      b.querySelector(".qtd").textContent = String(c === TODAS ? total : porCategoria.get(c) || 0);
    }
    const vazio = $("sem-temas");
    if (vazio) {
      vazio.hidden = visiveis > 0;
      if (!visiveis) {
        const ir = el("button", { type: "button", class: "botao-texto", texto: "Descrever com minhas palavras" });
        ir.addEventListener("click", () => {
          if (!campoTexto.value.trim()) campoTexto.value = campoFiltro.value.trim();
          atualizarTexto();
          campoTexto.focus();
        });
        vazio.replaceChildren(
          el("p", { style: "margin:0", texto: termo
            ? `Nenhum tema com “${campoFiltro.value.trim()}”${categoriaAtual !== TODAS ? ` em ${categoriaAtual}` : ""}. Que tal descrever com suas palavras?`
            : `Nenhum tema em ${categoriaAtual}.` }),
          termo ? ir : null,
        );
      }
    }
  }

  campoFiltro.addEventListener("input", filtrar);
  campoFiltro.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && campoFiltro.value) {
      ev.preventDefault();
      campoFiltro.value = "";
      filtrar();
    } else if (ev.key === "Enter") {
      // Enter na busca não envia o formulário; com um único tema visível, escolhe esse tema
      ev.preventDefault();
      const visiveis = areaTemas.querySelectorAll(".chip-alternar:not([hidden])");
      if (visiveis.length === 1) visiveis[0].click();
    }
  });

  // ================================================================ seleção de temas
  function alternarTema(nome) {
    if (selecionados.has(nome)) {
      selecionados.delete(nome);
      avisar("");
    } else if (selecionados.size >= MAX_TEMAS) {
      avisar(`Você já escolheu ${MAX_TEMAS} temas. Remova um para escolher outro.`);
      bandeja.classList.remove("balancar");
      void bandeja.offsetWidth;   // reinicia a animação
      bandeja.classList.add("balancar");
      return;
    } else {
      const usados = new Set(selecionados.values());
      let slot = 0;
      while (usados.has(slot)) slot++;
      selecionados.set(nome, slot);
      avisar("");
    }
    atualizarSelecao();
    esconderErro();
  }
  bandeja.addEventListener("animationend", () => bandeja.classList.remove("balancar"));

  let temporizadorAviso = 0;
  function avisar(msg) {
    clearTimeout(temporizadorAviso);
    avisoTemas.textContent = msg;
    if (msg) temporizadorAviso = setTimeout(() => { avisoTemas.textContent = ""; }, 5000);
  }

  function atualizarSelecao() {
    const cheio = selecionados.size >= MAX_TEMAS;
    for (const chip of areaTemas.querySelectorAll(".chip-alternar")) {
      const nome = chip.dataset.tema;
      const ativo = selecionados.has(nome);
      chip.setAttribute("aria-pressed", String(ativo));
      if (ativo) chip.dataset.slot = String(selecionados.get(nome));
      else delete chip.dataset.slot;
      if (cheio && !ativo) chip.setAttribute("aria-disabled", "true");
      else chip.removeAttribute("aria-disabled");
    }

    if (!selecionados.size) {
      listaSelecionados.replaceChildren(el("li", { class: "vazio-bandeja", texto: "Nenhum tema escolhido ainda" }));
    } else {
      listaSelecionados.replaceChildren(...[...selecionados].map(([nome, slot]) => {
        const remover = el("button", { type: "button", "aria-label": `Remover ${nome}` }, icone("x"));
        remover.addEventListener("click", () => {
          // mantém o foco num lugar previsível depois de remover
          const proximo = remover.closest("li").nextElementSibling || remover.closest("li").previousElementSibling;
          alternarTema(nome);
          const alvo = proximo && listaSelecionados.querySelector(`[aria-label="Remover ${CSS.escape(proximo.dataset.nome || "")}"]`);
          (alvo || campoFiltro).focus();
        });
        return el("li", { class: "token", "data-slot": String(slot), "data-nome": nome }, el("span", { texto: nome }), remover);
      }));
    }
    contadorTemas.textContent = `${selecionados.size}/${MAX_TEMAS}`;
    atualizarResumoPedido();
  }

  // ================================================================ texto livre e opções
  const suportaAutoAltura = window.CSS && CSS.supports && CSS.supports("field-sizing", "content");
  function atualizarTexto() {
    const n = campoTexto.value.length;
    const max = Number(campoTexto.maxLength) || 2000;
    contadorTexto.textContent = n ? `${n.toLocaleString("pt-BR")}/${max.toLocaleString("pt-BR")}` : "";
    contadorTexto.classList.toggle("perto", n > max * 0.9);
    if (!suportaAutoAltura) {
      campoTexto.style.height = "auto";
      campoTexto.style.height = `${Math.min(campoTexto.scrollHeight + 2, 320)}px`;
    }
    atualizarResumoPedido();
  }
  campoTexto.addEventListener("input", () => { atualizarTexto(); if (campoTexto.value.trim()) esconderErro(); });

  for (const b of document.querySelectorAll(".exemplo")) {
    b.addEventListener("click", () => {
      const atualTexto = campoTexto.value.trim();
      campoTexto.value = atualTexto ? `${atualTexto.replace(/[;,.\s]+$/, "")}; ${b.textContent}` : b.textContent;
      atualizarTexto();
      esconderErro();
      campoTexto.focus();
      campoTexto.setSelectionRange(campoTexto.value.length, campoTexto.value.length);
    });
  }

  const topK = () => Number((form.querySelector('input[name="top-k"]:checked') || {}).value || 5);
  function anoMin() {
    const v = parseInt(campoAno.value, 10);
    return Number.isNaN(v) ? null : v;
  }
  function atualizarOpcoes() {
    const ano = anoMin();
    resumoOpcoes.textContent = `${topK()} professores · ${ano ? `desde ${ano}` : "qualquer ano"}`;
  }
  form.addEventListener("change", (ev) => {
    if (ev.target.name === "top-k" || ev.target === campoAno) atualizarOpcoes();
  });
  campoAno.addEventListener("input", atualizarOpcoes);

  function atualizarResumoPedido() {
    const n = selecionados.size;
    const temTexto = Boolean(campoTexto.value.trim());
    const partes = [];
    if (n) partes.push(el("strong", { texto: plural(n, ["tema", "temas"]) }));
    if (temTexto) partes.push(el("strong", { texto: "seu texto" }));
    if (!partes.length) {
      resumoPedido.replaceChildren("Escolha um tema ou descreva seu interesse.");
      botao.classList.add("pendente");
    } else {
      resumoPedido.replaceChildren("Buscar por ", ...partes.flatMap((p, i) => (i ? [" e ", p] : [p])));
      botao.classList.remove("pendente");
    }
  }

  // ================================================================ envio
  function mostrarErro(msg) {
    erroForm.textContent = msg;
    erroForm.hidden = false;
    erroForm.focus({ preventScroll: true });
    erroForm.scrollIntoView({ behavior: reduzirMovimento.matches ? "auto" : "smooth", block: "nearest" });
  }
  function esconderErro() { erroForm.hidden = true; }

  function mensagemDeErro(dados, statusHttp) {
    const d = dados && dados.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) return d.map((x) => x.msg).join("; ");
    return `A busca falhou (HTTP ${statusHttp}). Tente novamente em instantes.`;
  }

  function definirOcupado(sim) {
    ocupado = sim;
    botao.classList.toggle("ocupado", sim);
    botao.setAttribute("aria-disabled", String(sim));
    botao.querySelector("span").textContent = sim ? "Buscando…" : (atual ? "Atualizar resultado" : "Buscar orientadores");
  }

  let relogio = 0;
  function iniciarCarregamento() {
    const inicio = performance.now();
    statusEtapa.textContent = ETAPAS[0][1];
    cronometro.textContent = "";
    relogio = setInterval(() => {
      const ms = performance.now() - inicio;
      cronometro.textContent = `(${Math.round(ms / 1000)} s)`;
      const etapa = ETAPAS.filter(([t]) => ms >= t).pop();
      if (etapa && statusEtapa.textContent !== etapa[1]) statusEtapa.textContent = etapa[1];
    }, 500);
    transicao(() => {
      document.body.classList.add("com-resultado");
      resultado.hidden = true;
      status.hidden = false;
    }).then(() => {
      if (!telaLarga.matches && !status.hidden) {
        status.scrollIntoView({ behavior: reduzirMovimento.matches ? "auto" : "smooth", block: "start" });
      }
    });
    return inicio;
  }

  function encerrarCarregamento() {
    clearInterval(relogio);
    status.hidden = true;
  }

  $("cancelar").addEventListener("click", () => { if (controlador) controlador.abort(); });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (ocupado) return;
    esconderErro();
    const texto = campoTexto.value.trim();
    if (!selecionados.size && !texto) {
      mostrarErro("Escolha pelo menos um tema ou descreva seu interesse no campo de texto.");
      return;
    }
    const pedido = { top_k: topK(), n_itens: N_ITENS };
    if (selecionados.size) pedido.topicos = [...selecionados.keys()];
    if (texto) pedido.texto = texto;
    const ano = anoMin();
    if (ano !== null) pedido.ano_min = ano;
    const ctx = { slots: new Map(selecionados) };

    definirOcupado(true);
    controlador = new AbortController();
    const inicio = iniciarCarregamento();

    try {
      const resp = await fetch(`${API}/recomendar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pedido),
        signal: controlador.signal,
      });
      const dados = await resp.json().catch(() => null);
      if (!resp.ok) throw new Error(mensagemDeErro(dados, resp.status));
      ctx.segundos = (performance.now() - inicio) / 1000;
      encerrarCarregamento();
      atual = { dados, pedido, ctx };
      await transicao(() => desenharResultado(dados, pedido, ctx));
      requestAnimationFrame(() => {
        tituloResultado.focus({ preventScroll: true });
        const alvo = telaLarga.matches ? resultado : tituloResultado;
        alvo.scrollIntoView({ behavior: reduzirMovimento.matches ? "auto" : "smooth", block: "start" });
      });
    } catch (e) {
      encerrarCarregamento();
      // volta ao último resultado (ou ao formulário sozinho, se ainda não havia nenhum)
      transicao(() => {
        if (atual) resultado.hidden = false;
        else document.body.classList.remove("com-resultado");
      });
      if (e.name === "AbortError") {
        avisar("Busca cancelada.");
        botao.focus();
      } else {
        mostrarErro(e instanceof TypeError
          ? "Não foi possível falar com o servidor. Confira a conexão ou se a API está no ar."
          : e.message);
      }
    } finally {
      controlador = null;
      definirOcupado(false);
    }
  });

  $("editar-busca").addEventListener("click", () => {
    if (!telaLarga.matches) form.scrollIntoView({ behavior: reduzirMovimento.matches ? "auto" : "smooth", block: "start" });
    campoFiltro.focus({ preventScroll: !telaLarga.matches });
  });

  // ================================================================ resultado
  function nivelAfinidade(p) {
    if (p >= 80) return "alta";
    if (p >= 55) return "média";
    return "moderada";
  }

  function nivelCobertura(rel) {
    if (rel >= 0.75) return "forte";
    if (rel >= 0.4) return "média";
    if (rel > 0) return "fraca";
    return "sem evidência";
  }

  function medidor(valor, rotulo, slot) {
    return el("div", {
      class: "medidor", role: "meter", "aria-label": rotulo,
      "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(valor * 100)),
      "data-slot": slot,
    }, el("span", { style: `--v:${Math.max(0, Math.min(1, valor)).toFixed(3)}` }));
  }

  // dados derivados usados no cartão e na comparação
  function analisar(dados, pedido, ctx) {
    const ranking = dados.ranking || [];
    const topicos = [...(pedido.topicos || [])];
    if (pedido.texto) topicos.push(NOME_TEXTO_LIVRE);
    const slot = (t) => (t === NOME_TEXTO_LIVRE ? "t" : ctx.slots.has(t) ? String(ctx.slots.get(t)) : undefined);
    const maior = Math.max(...ranking.map((p) => p.score || 0)) || 1;
    const maxTopico = Object.fromEntries(topicos.map((t) =>
      [t, Math.max(...ranking.map((p) => (p.scores_topicos || {})[t] || 0)) || 0]));

    const profs = ranking.map((p) => {
      const percentual = Math.max(4, Math.round(((p.score || 0) / maior) * 100));
      const cobertura = topicos.map((t) => {
        const v = (p.scores_topicos || {})[t] || 0;
        const rel = maxTopico[t] ? v / maxTopico[t] : 0;
        return { topico: t, rel, nivel: nivelCobertura(rel), slot: slot(t) };
      });
      const disciplinas = new Set();
      for (const det of Object.values(p.topicos || {})) {
        for (const d of det.disciplinas_tema || []) disciplinas.add(tituloNome(d));
      }
      const destaques = p.destaques || {};
      const contagens = ORDEM_TIPOS.filter((t) => (destaques[t] || []).length)
        .map((t) => ({ tipo: t, n: destaques[t].length }));
      const perfil = p.perfil || {};
      const parcela = typeof perfil.parcela_do_score === "number" && perfil.parcela_do_score > 0 && perfil.parcela_do_score <= 1
        ? perfil.parcela_do_score : null;
      return {
        bruto: p, nome: tituloNome(p.nome || p.professor_id), posicao: p.posicao,
        percentual, cobertura, disciplinas: [...disciplinas], destaques, contagens, parcela,
        perfilAlinhado: (perfil.score || 0) >= 0.5,
      };
    });
    return { profs, topicos, slot, varios: topicos.length > 1 };
  }

  function desenharResultado(dados, pedido, ctx) {
    document.body.classList.add("com-resultado");
    const analise = analisar(dados, pedido, ctx);
    atual.analise = analise;
    comparados.clear();
    atualizarBarraComparar();

    // cabeçalho
    const n = analise.profs.length;
    const meta = [n ? plural(n, ["professor", "professores"]) : "Nenhum professor"];
    if (pedido.ano_min) meta.push(`trabalhos desde ${pedido.ano_min}`);
    if (ctx.segundos) meta.push(`${ctx.segundos.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`);
    metaResultado.textContent = meta.join(" · ");
    resumoBusca.replaceChildren(...analise.topicos.map((t) => el("li", {
      class: `etiqueta${t === NOME_TEXTO_LIVRE ? " texto-livre" : ""}`, "data-slot": analise.slot(t),
      title: t === NOME_TEXTO_LIVRE ? pedido.texto : t,
    }, el("span", { texto: t === NOME_TEXTO_LIVRE ? `“${pedido.texto}”` : t }))));

    // lista
    if (!n) {
      const sugestoes = [
        el("li", { texto: "Use outras palavras ou termos mais gerais no texto." }),
        el("li", { texto: "Troque ou remova algum dos temas escolhidos." }),
      ];
      let semAno = null;
      if (pedido.ano_min) {
        sugestoes.unshift(el("li", { texto: `Remova o filtro de ano (desde ${pedido.ano_min}).` }));
        semAno = el("button", { type: "button", class: "botao-secundario", texto: "Buscar sem o filtro de ano" });
        semAno.addEventListener("click", () => { campoAno.value = ""; atualizarOpcoes(); form.requestSubmit(); });
      }
      lista.replaceChildren(el("li", { class: "vazio-resultado" },
        el("h3", { texto: "Nenhum professor com evidências suficientes" }),
        el("p", { texto: "Algumas ideias para tentar de novo:" }),
        el("ul", {}, sugestoes),
        semAno,
      ));
      botaoAlternarTodos.hidden = true;
    } else {
      lista.replaceChildren(...analise.profs.map((p, i) => cartaoProfessor(p, i, analise)));
      botaoAlternarTodos.hidden = n < 2;
      atualizarBotaoTodos();
    }

    const cortados = (dados.professores_cortados || []).length;
    notaCortados.hidden = !cortados || !n;
    notaCortados.textContent = cortados
      ? `${plural(cortados, ["outro professor também teve", "outros professores também tiveram"])} evidências, mas com afinidade bem abaixo dos primeiros, e ${cortados === 1 ? "ficou" : "ficaram"} de fora da lista.`
      : "";

    resultado.hidden = false;
    botao.querySelector("span").textContent = "Atualizar resultado";
  }

  function cartaoProfessor(p, i, analise) {
    const idNome = `prof-${i}-nome`;

    const resumo = p.contagens.length
      ? p.contagens.map(({ tipo, n }) => plural(n, CONTAGEM_TIPO[tipo])).join(" · ") + " em destaque"
      : "Recomendado pelo perfil";

    const marcar = el("input", { type: "checkbox", "data-indice": String(i), "aria-describedby": idNome });
    marcar.addEventListener("change", () => alternarComparacao(i, marcar));

    const selos = [];
    if (p.disciplinas.length) {
      selos.push(el("span", { class: "selo" }, icone("livro"), el("span", { texto: `Leciona ${listaHumana(p.disciplinas)}` })));
    }
    if (p.perfilAlinhado) selos.push(el("span", { class: "selo neutro" }, icone("check"), el("span", { texto: "Perfil alinhado ao tema" })));

    const cabeca = el("div", { class: "prof-cabeca" },
      el("div", { class: "posicao", "aria-label": `${p.posicao}º lugar` },
        document.createTextNode(String(p.posicao)), el("sup", { "aria-hidden": "true", texto: "º" })),
      el("div", { class: "prof-titulo" },
        el("h3", { id: idNome, texto: p.nome }),
        el("p", { class: "prof-resumo", texto: resumo })),
      el("label", { class: "comparar" }, marcar, el("span", { texto: "Comparar" })),
      el("div", { class: "afinidade" },
        el("span", { class: "nivel", texto: `Afinidade ${nivelAfinidade(p.percentual)}` }),
        medidor(p.percentual / 100, `Afinidade relativa: ${p.percentual}%`),
        el("strong", { texto: `${p.percentual}%` })),
      selos.length ? el("div", { class: "selos" }, selos) : null,
    );

    const porque = el("details", { class: "porque", open: i === 0 },
      el("summary", {}, el("span", { texto: "Por que este professor?" })),
      el("div", { class: "porque-conteudo" },
        analise.varios ? blocoCobertura(p) : null,
        p.parcela !== null ? blocoPerfil(p) : null,
        blocoEvidencias(p, analise)),
    );
    porque.addEventListener("toggle", atualizarBotaoTodos);

    return el("li", { class: "professor", style: `--i:${i}` },
      el("article", { "aria-labelledby": idNome },
        el("div", { class: "professor-corpo" }, cabeca),
        porque));
  }

  function blocoCobertura(p) {
    const grupos = { forte: [], "média": [], fraca: [] };
    for (const c of p.cobertura) {
      if (grupos[c.nivel]) grupos[c.nivel].push(c.topico === NOME_TEXTO_LIVRE ? "seu texto" : c.topico);
    }
    const frases = [];
    if (grupos.forte.length) frases.push(`Forte em ${listaHumana(grupos.forte)}`);
    if (grupos["média"].length) frases.push(`${frases.length ? "média" : "Média"} em ${listaHumana(grupos["média"])}`);
    if (grupos.fraca.length) frases.push(`${frases.length ? "pouca" : "Pouca"} evidência em ${listaHumana(grupos.fraca)}`);

    return el("section", {},
      el("h4", { class: "bloco-titulo", texto: "Cobertura dos seus temas, comparada aos demais" }),
      frases.length ? el("p", { class: "frase-cobertura", texto: frases.join(" · ") + "." }) : null,
      el("ul", { class: "coberturas" }, p.cobertura.map((c) => el("li", { class: "cobertura", "data-slot": c.slot },
        el("span", { class: "cobertura-nome" }, el("span", { texto: nomeTopico(c.topico), title: nomeTopico(c.topico) })),
        medidor(c.rel, `${nomeTopico(c.topico)}: cobertura ${c.nivel}`, c.slot),
        el("span", { class: "cobertura-nivel", texto: c.nivel }),
      ))),
    );
  }

  function blocoPerfil(p) {
    const perc = Math.round(p.parcela * 100);
    return el("section", {},
      el("h4", { class: "bloco-titulo", texto: "De onde vem a afinidade" }),
      el("div", { class: "barra-composicao", "aria-hidden": "true" },
        el("span", { style: `width:${perc}%` }), el("span", { style: `width:${100 - perc}%` })),
      el("ul", { class: "legenda-composicao" },
        el("li", { texto: `Perfil do professor · ~${perc}%` }),
        el("li", { texto: `Produções, projetos e demais evidências · ~${100 - perc}%` })),
      el("p", { class: "sr-only", texto: `O texto de perfil do professor responde por cerca de ${perc}% da afinidade; o restante vem das evidências.` }),
    );
  }

  function blocoEvidencias(p, analise) {
    const blocos = ORDEM_TIPOS
      .filter((tipo) => (p.destaques[tipo] || []).length)
      .map((tipo) => el("div", { class: "evidencia" },
        el("h4", {}, el("span", { texto: ROTULO_TIPO[tipo] || tipo }), el("span", { class: "qtd", texto: String(p.destaques[tipo].length) })),
        el("ul", {}, p.destaques[tipo].map((item) => itemEvidencia(item, analise))),
      ));
    return el("section", {},
      el("h4", { class: "bloco-titulo", texto: "Evidências em destaque" }),
      blocos.length
        ? el("div", { class: "evidencias" }, blocos)
        : el("p", { class: "sem-evidencias", texto: "Recomendado pelo perfil do professor (sem itens específicos para destacar)." }));
  }

  function itemEvidencia(item, analise) {
    const meta = [];
    if (ROTULO_SUBTIPO[item.subtipo]) meta.push(el("li", { texto: ROTULO_SUBTIPO[item.subtipo] }));
    if (item.disciplina_do_tema) meta.push(el("li", { class: "tag-disciplina", texto: "disciplina do tema" }));
    if (analise.varios && item.topico) {
      meta.push(el("li", { class: "tag-tema", "data-slot": analise.slot(item.topico), texto: nomeTopico(item.topico) }));
    }
    if (item.corte === "melhor_do_tipo") {
      meta.push(el("li", { class: "tag-fraca", title: "Ficou abaixo do corte de relevância, mas é o melhor item deste tipo", texto: "relação mais fraca" }));
    }
    return el("li", { class: "item", "data-slot": analise.varios && item.topico ? analise.slot(item.topico) : undefined },
      el("p", { class: "item-titulo" },
        item.codigo ? el("span", { class: "codigo", texto: item.codigo }) : null,
        document.createTextNode(primeiraMaiuscula(item.titulo || "(sem título)"))),
      meta.length ? el("ul", { class: "item-meta", "aria-label": "Detalhes" }, meta) : null,
    );
  }

  function atualizarBotaoTodos() {
    const todos = [...lista.querySelectorAll(".porque")];
    const abertos = todos.filter((d) => d.open).length;
    botaoAlternarTodos.textContent = abertos === todos.length ? "Recolher todos" : "Abrir todos";
  }
  botaoAlternarTodos.addEventListener("click", () => {
    const todos = [...lista.querySelectorAll(".porque")];
    const abrir = todos.some((d) => !d.open);
    for (const d of todos) d.open = abrir;
    atualizarBotaoTodos();
  });

  // ================================================================ comparação
  function alternarComparacao(i, caixa) {
    if (caixa.checked) {
      if (comparados.size >= MAX_COMPARAR) {
        caixa.checked = false;
        atualizarBarraComparar(`Compare até ${MAX_COMPARAR} professores por vez.`);
        return;
      }
      comparados.add(i);
    } else {
      comparados.delete(i);
    }
    atualizarBarraComparar();
  }

  function atualizarBarraComparar(alerta) {
    const n = comparados.size;
    barraComparar.hidden = n === 0;
    const partes = [document.createTextNode(n === 1 ? "1 selecionado · marque mais um" : `${n} selecionados`)];
    if (alerta) partes.push(document.createTextNode(" · "), el("span", { class: "alerta", texto: alerta }));
    textoComparar.replaceChildren(...partes);
    botaoComparar.setAttribute("aria-disabled", String(n < 2));
  }

  $("limpar-comparacao").addEventListener("click", () => {
    comparados.clear();
    for (const c of lista.querySelectorAll(".comparar input")) c.checked = false;
    atualizarBarraComparar();
  });

  botaoComparar.addEventListener("click", () => {
    if (comparados.size < 2 || !atual || !atual.analise) {
      atualizarBarraComparar("Marque pelo menos 2 professores.");
      return;
    }
    const profs = [...comparados].sort((a, b) => a - b).map((i) => atual.analise.profs[i]);
    tabelaComparar.replaceChildren(tabelaComparacao(profs, atual.analise));
    dialogo.showModal();
    tabelaComparar.scrollTo(0, 0);
  });

  $("fechar-comparacao").addEventListener("click", () => dialogo.close());
  dialogo.addEventListener("click", (ev) => { if (ev.target === dialogo) dialogo.close(); });   // clique no fundo

  function tabelaComparacao(profs, analise) {
    const linhas = [];
    const linha = (rotulo, celulas) => linhas.push(el("tr", {},
      el("th", { scope: "row", texto: rotulo }), celulas.map((c) => el("td", {}, c))));
    const secao = (rotulo) => linhas.push(el("tr", { class: "secao" },
      el("th", { scope: "rowgroup", colspan: String(profs.length + 1), texto: rotulo })));
    const melhorEntre = (valores) => Math.max(...valores);

    const maxAfin = melhorEntre(profs.map((p) => p.percentual));
    linha("Afinidade relativa", profs.map((p) => el("div", {},
      el("span", { class: p.percentual === maxAfin ? "melhor" : null, texto: `${p.percentual}% · ${nivelAfinidade(p.percentual)}` }),
      medidor(p.percentual / 100, `Afinidade de ${p.nome}: ${p.percentual}%`))));

    if (analise.varios) {
      secao("Cobertura dos temas");
      analise.topicos.forEach((t, k) => {
        const maxRel = melhorEntre(profs.map((p) => p.cobertura[k].rel));
        linha(nomeTopico(t), profs.map((p) => {
          const c = p.cobertura[k];
          return el("div", { class: "celula-cobertura", "data-slot": c.slot },
            el("span", { class: c.rel === maxRel && c.rel > 0 ? "melhor" : null, texto: c.nivel }),
            medidor(c.rel, `${p.nome}, ${nomeTopico(t)}: ${c.nivel}`, c.slot));
        }));
      });
    }

    secao("Perfil e disciplinas");
    linha("Peso do perfil", profs.map((p) => (p.parcela !== null
      ? document.createTextNode(`~${Math.round(p.parcela * 100)}% da afinidade`)
      : el("span", { class: "vazio-celula", texto: "—" }))));
    linha("Leciona do tema", profs.map((p) => (p.disciplinas.length
      ? el("ul", {}, p.disciplinas.map((d) => el("li", { texto: d })))
      : el("span", { class: "vazio-celula", texto: "Nenhuma" }))));

    const tipos = ORDEM_TIPOS.filter((t) => profs.some((p) => (p.destaques[t] || []).length));
    if (tipos.length) {
      secao("Melhor evidência de cada tipo");
      for (const tipo of tipos) {
        linha(ROTULO_TIPO[tipo] || tipo, profs.map((p) => {
          const itens = p.destaques[tipo] || [];
          if (!itens.length) return el("span", { class: "vazio-celula", texto: "—" });
          const it = itens[0];
          return el("div", {},
            it.codigo ? el("span", { class: "codigo", texto: it.codigo }) : null,
            document.createTextNode(primeiraMaiuscula(it.titulo || "(sem título)")),
            itens.length > 1 ? el("div", { class: "vazio-celula", texto: `+${itens.length - 1} em destaque` }) : null);
        }));
      }
    }

    return el("table", { class: "tabela-comparar" },
      el("caption", { class: "sr-only", texto: `Comparação entre ${listaHumana(profs.map((p) => p.nome))}` }),
      el("thead", {}, el("tr", {},
        el("th", { scope: "col" }, el("span", { class: "sr-only", texto: "Critério" })),
        profs.map((p) => el("th", { scope: "col" },
          el("span", { class: "posicao-mini", texto: `${p.posicao}º lugar` }),
          document.createTextNode(p.nome))))),
      el("tbody", {}, linhas),
    );
  }

  // ================================================================ início
  atualizarTexto();
  atualizarOpcoes();
  atualizarSelecao();
  carregarTemas();
})();
