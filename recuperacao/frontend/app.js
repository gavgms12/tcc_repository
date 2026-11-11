// Questionário do aluno: escolhe temas do catálogo e/ou escreve um texto livre,
// envia para POST /recomendar e mostra os professores recomendados.
//
// Endereço da API:
//   - servido pela própria API (/app/): mesmo endereço, nada a configurar;
//   - aberto de outro lugar: ?api=https://xxxx.trycloudflare.com na URL;
//   - aberto como arquivo (file://): http://localhost:8000.
(() => {
  "use strict";

  const MAX_TEMAS = 3;
  const N_ITENS = 3;
  const NOME_TEXTO_LIVRE = "Texto livre";

  const ROTULO_TIPO = {
    producao: "Produções",
    projeto: "Projetos",
    orientacao: "Orientações",
    trabalho: "Iniciação científica",
    disciplina: "Disciplinas",
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

  const API = (() => {
    const param = new URLSearchParams(location.search).get("api");
    if (param) return param.replace(/\/+$/, "");
    if (location.protocol === "file:") return "http://localhost:8000";
    return "";
  })();

  const $ = (id) => document.getElementById(id);
  const form = $("questionario");
  const areaTemas = $("temas");
  const contador = $("contador-temas");
  const campoTexto = $("texto");
  const erroForm = $("erro-formulario");
  const botao = $("buscar");
  const status = $("status");
  const cronometro = $("cronometro");
  const resultado = $("resultado");
  const lista = $("lista-professores");
  const resumoBusca = $("resumo-busca");

  const selecionados = new Set();
  let detalhesTemas = [];

  $("limite-temas").textContent = String(MAX_TEMAS);

  // Cria um elemento; textos sempre por textContent (nada da base vira HTML).
  function el(tag, attrs = {}, ...filhos) {
    const no = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") no.className = v;
      else if (k === "texto") no.textContent = v;
      else no.setAttribute(k, v === true ? "" : v);
    }
    for (const f of filhos.flat()) if (f) no.append(f);
    return no;
  }

  // ---------------------------------------------------------------- temas
  async function carregarTemas() {
    try {
      const resp = await fetch(`${API}/topicos`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const dados = await resp.json();
      detalhesTemas = dados.detalhes || (dados.topicos || []).map((nome) => ({ nome, categoria: "Temas" }));
      desenharTemas();
    } catch (e) {
      areaTemas.replaceChildren(el("p", {
        class: "erro",
        texto: "Não foi possível carregar os temas. Confira se a API está no ar" +
          (API ? ` (${API})` : "") + ". Você ainda pode buscar pelo texto livre.",
      }));
    }
  }

  function desenharTemas() {
    const porCategoria = new Map();
    for (const t of detalhesTemas) {
      if (!porCategoria.has(t.categoria)) porCategoria.set(t.categoria, []);
      porCategoria.get(t.categoria).push(t);
    }
    const grupos = [...porCategoria.entries()]
      .sort(([a], [b]) => a.localeCompare(b, "pt-BR"))
      .map(([categoria, temas]) => el("div", { class: "grupo-temas" },
        el("h3", { texto: categoria }),
        el("div", { class: "chips" },
          temas
            .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"))
            .map((t) => {
              const chip = el("button", {
                type: "button", class: "chip", "aria-pressed": "false",
                title: t.descricao || t.nome, "data-tema": t.nome, texto: t.nome,
              });
              chip.addEventListener("click", () => alternarTema(t.nome));
              return chip;
            })),
      ));
    areaTemas.replaceChildren(...grupos, el("p", { class: "descricao-tema", id: "descricao-tema", hidden: true }));
    atualizarChips();
  }

  function alternarTema(nome) {
    if (selecionados.has(nome)) selecionados.delete(nome);
    else if (selecionados.size < MAX_TEMAS) selecionados.add(nome);
    atualizarChips(nome);
    esconderErro();
  }

  function atualizarChips(ultimo) {
    const cheio = selecionados.size >= MAX_TEMAS;
    for (const chip of areaTemas.querySelectorAll(".chip")) {
      const ativo = selecionados.has(chip.dataset.tema);
      chip.setAttribute("aria-pressed", String(ativo));
      chip.disabled = cheio && !ativo;
    }
    contador.textContent = selecionados.size
      ? `${selecionados.size} de ${MAX_TEMAS} selecionado(s): ${[...selecionados].join(", ")}`
      : "";
    const caixa = $("descricao-tema");
    const tema = detalhesTemas.find((t) => t.nome === ultimo);
    if (caixa) {
      if (tema && selecionados.has(tema.nome) && tema.descricao) {
        caixa.textContent = `${tema.nome}: ${tema.descricao}`;
        caixa.hidden = false;
      } else {
        caixa.hidden = true;
      }
    }
  }

  // ---------------------------------------------------------------- envio
  function mostrarErro(msg) {
    erroForm.textContent = msg;
    erroForm.hidden = false;
  }
  function esconderErro() {
    erroForm.hidden = true;
  }

  function mensagemDeErro(dados, statusHttp) {
    const d = dados && dados.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) return d.map((x) => x.msg).join("; ");
    return `A busca falhou (HTTP ${statusHttp}). Tente novamente em instantes.`;
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    esconderErro();
    const texto = campoTexto.value.trim();
    if (!selecionados.size && !texto) {
      mostrarErro("Escolha pelo menos um tema ou descreva seu interesse no campo de texto.");
      return;
    }
    const pedido = { top_k: Number($("top-k").value), n_itens: N_ITENS };
    if (selecionados.size) pedido.topicos = [...selecionados];
    if (texto) pedido.texto = texto;
    const anoMin = parseInt($("ano-min").value, 10);
    if (!Number.isNaN(anoMin)) pedido.ano_min = anoMin;

    botao.disabled = true;
    resultado.hidden = true;
    status.hidden = false;
    const inicio = Date.now();
    cronometro.textContent = "";
    const relogio = setInterval(() => {
      cronometro.textContent = `(${Math.round((Date.now() - inicio) / 1000)} s)`;
    }, 1000);

    try {
      const resp = await fetch(`${API}/recomendar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pedido),
      });
      const dados = await resp.json().catch(() => null);
      if (!resp.ok) throw new Error(mensagemDeErro(dados, resp.status));
      desenharResultado(dados, pedido);
    } catch (e) {
      mostrarErro(e instanceof TypeError
        ? "Não foi possível falar com o servidor. Confira a conexão ou se a API está no ar."
        : e.message);
    } finally {
      clearInterval(relogio);
      status.hidden = true;
      botao.disabled = false;
    }
  });

  // ---------------------------------------------------------------- resultado
  function desenharResultado(dados, pedido) {
    const ranking = dados.ranking || [];
    const partes = [];
    if (pedido.topicos) partes.push(`temas: ${pedido.topicos.join(", ")}`);
    if (pedido.texto) partes.push(`texto: “${pedido.texto}”`);
    resumoBusca.textContent = `Busca por ${partes.join(" · ")}`;

    if (!ranking.length) {
      lista.replaceChildren(el("li", { class: "vazio", texto:
        "Nenhum professor com evidências suficientes para esta busca. Tente outras palavras ou outros temas." }));
    } else {
      const maior = Math.max(...ranking.map((p) => p.score || 0)) || 1;
      const variosTopicos = Object.keys(ranking[0].topicos || {}).length > 1;
      lista.replaceChildren(...ranking.map((p) => cartaoProfessor(p, maior, variosTopicos)));
    }
    resultado.hidden = false;
    resultado.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function cartaoProfessor(prof, maior, variosTopicos) {
    const percentual = Math.max(4, Math.round(((prof.score || 0) / maior) * 100));
    const barra = el("div", { class: "barra", role: "img", "aria-label": `Afinidade relativa ${percentual}%` },
      el("span", { style: `width:${percentual}%` }));

    return el("li", { class: "professor" },
      el("div", { class: "professor-topo" },
        el("div", { class: "posicao", texto: `${prof.posicao}º` }),
        el("div", { class: "professor-info" },
          el("h3", { texto: tituloNome(prof.nome || prof.professor_id) }),
          el("div", { class: "afinidade" }, el("span", { texto: "Afinidade" }), barra, el("span", { texto: `${percentual}%` })),
          selos(prof),
        ),
      ),
      evidencias(prof, variosTopicos),
    );
  }

  function selos(prof) {
    const lista = [];
    const disciplinas = new Set();
    for (const det of Object.values(prof.topicos || {})) {
      for (const d of det.disciplinas_tema || []) disciplinas.add(tituloNome(d));
    }
    if (disciplinas.size) {
      lista.push(el("span", { class: "selo", texto: `Leciona: ${[...disciplinas].join(", ")}` }));
    }
    const perfil = prof.perfil || {};
    if ((perfil.score || 0) >= 0.5) {
      lista.push(el("span", { class: "selo neutro", texto: "Perfil alinhado ao tema" }));
    }
    return lista.length ? el("div", { class: "selos" }, lista) : null;
  }

  function evidencias(prof, variosTopicos) {
    const destaques = prof.destaques || {};
    const blocos = ORDEM_TIPOS
      .filter((tipo) => (destaques[tipo] || []).length)
      .map((tipo) => el("div", { class: "evidencia" },
        el("h4", { texto: ROTULO_TIPO[tipo] || tipo }),
        el("ul", {}, destaques[tipo].map((item) => itemEvidencia(item, variosTopicos))),
      ));
    if (!blocos.length) {
      return el("p", { class: "sem-evidencias", texto: "Recomendado pelo perfil do professor (sem itens específicos para destacar)." });
    }
    return el("div", { class: "evidencias" }, blocos);
  }

  function itemEvidencia(item, variosTopicos) {
    const meta = [];
    if (ROTULO_SUBTIPO[item.subtipo]) meta.push(el("span", { texto: ROTULO_SUBTIPO[item.subtipo] }));
    if (item.disciplina_do_tema) meta.push(el("span", { class: "tag-tema", texto: "disciplina do tema" }));
    if (variosTopicos && item.topico) {
      meta.push(el("span", { texto: item.topico === NOME_TEXTO_LIVRE ? "seu texto" : item.topico }));
    }
    return el("li", {},
      el("div", {},
        item.codigo ? el("span", { class: "codigo", texto: item.codigo }) : null,
        document.createTextNode(primeiraMaiuscula(item.titulo || "(sem título)")),
      ),
      meta.length ? el("div", { class: "item-meta" }, meta) : null,
    );
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

  carregarTemas();
})();
