import re

import numpy as np
import pandas as pd
from FlagEmbedding import FlagReranker

from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.busca.agregacao import decaimento_da_fonte, media_decaimento
from recuperacao.sistema_de_busca.database_vetores import buscar_payloads_varios
from recuperacao.sistema_de_busca.busca.cache_rerank import cache_disco, chave


def carregar_reranker() -> FlagReranker:
    return FlagReranker(config.RERANKER_MODEL, use_fp16=True, normalize=True)


def _top_n(rel: pd.DataFrame, ids_prof: list[str], n: int) -> pd.DataFrame:
    rel = rel[rel["professor_id"].isin(ids_prof)]
    return rel.sort_values("score", ascending=False).groupby("professor_id").head(n)


def _selecoes(ranking: pd.DataFrame, rels: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Os n melhores itens de cada tipo, por professor do ranking."""
    ids_prof = ranking["professor_id"].tolist()
    return {tipo: _top_n(rels[tipo], ids_prof, cfg["n"]) for tipo, cfg in config.FONTES_ITENS.items()}


def ids_candidatos(ranking: pd.DataFrame, rels_por_topico: dict[str, dict[str, pd.DataFrame]]) -> dict[str, list]:
    """{coleção: ids} de tudo que criar_candidatos vai precisar, somando todos os tópicos
    (para buscar os payloads uma vez só, em vez de uma vez por tópico)."""
    pedidos = {config.COLLECTION_PROFESSORES: ranking["professor_id"].tolist()}
    for rels in rels_por_topico.values():
        for tipo, selecao in _selecoes(ranking, rels).items():
            pedidos.setdefault(config.FONTES_ITENS[tipo]["collection"], []).extend(selecao["objeto_id"])
    return pedidos


def criar_candidatos(client, ranking: pd.DataFrame, rels: dict[str, pd.DataFrame],
                     payloads: dict[str, dict[str, dict]] | None = None) -> list[dict]:
    """Lista plana: perfil + melhores itens de cada tipo, cada um com seu texto.

    payloads: {coleção: {id: payload}} já buscados (ver ids_candidatos); None busca aqui.
    """
    ids_prof = ranking["professor_id"].tolist()
    selecoes = _selecoes(ranking, rels)
    if payloads is None:
        payloads = buscar_payloads_varios(client, {
            config.COLLECTION_PROFESSORES: ids_prof,
            **{config.FONTES_ITENS[tipo]["collection"]: sel["objeto_id"].tolist() for tipo, sel in selecoes.items()},
        })
    perfis = payloads.get(config.COLLECTION_PROFESSORES, {})
    nomes = {pid: p.get("nome") for pid, p in perfis.items()}

    candidatos = []

    for pid in ids_prof:
        perfil = perfis.get(pid)
        if perfil and perfil.get("texto"):
            candidatos.append({
                "professor_id": pid, "professor_nome": nomes.get(pid),
                "tipo": "professor", "item_id": pid, "texto": perfil["texto"],
            })

    for tipo, cfg in config.FONTES_ITENS.items():
        da_colecao = payloads.get(cfg["collection"], {})

        for _, rel in selecoes[tipo].iterrows():
            item = da_colecao.get(rel["objeto_id"])
            pid = rel["professor_id"]
            if pid not in perfis or not item or not item.get("texto"):
                continue
            candidatos.append({
                "professor_id": pid, "professor_nome": nomes.get(pid),
                "tipo": tipo, "item_id": rel["objeto_id"], "texto": item["texto"],
                "titulo": item.get("titulo") or item.get("nome"),
                "subtipo": item.get("tipo"),                       # livro, artigo_periodico, pesquisa...
                "codigo": item.get("codigo"),                      # sigla da disciplina (ex.: DIM0110)
                "peso_tipo": config.peso_interno(tipo, item),
            })

    return candidatos


_cache_scores: dict[tuple[str, str], float] = {}
RERANK_MAX_LENGTH = 512
estatisticas = {"pares_calculados": 0, "pares_do_disco": 0}   # modelo x lidos do cache em disco


# Frases que dizem a intenção do aluno, não o tema ("quero pesquisar ...", "tenho interesse em ...").
# Atrapalham o reranker: ele compara o item com a frase inteira.
_INTENCAO = re.compile(
    r"\b(?:eu\s+)?(?:quero|queria|gostaria\s+de|pretendo|desejo|tenho\s+interesse\s+(?:em|por)|"
    r"me\s+interesso\s+(?:por|em)|meu\s+interesse\s+[ée])"
    r"(?:\s+(?:pesquisar|estudar|trabalhar|aprender|fazer|desenvolver|atuar|seguir)"
    r"(?:\s+(?:um|uma)\s+(?:tcc|trabalho|pesquisa|projeto|ic|inicia[çc][ãa]o\s+cient[íi]fica))?)?"
    r"(?:\s+(?:sobre|com|em|na\s+[áa]rea\s+de|no|na|de))?\s*",
    re.IGNORECASE,
)


def partes_texto_livre(texto: str) -> list[str]:
    """Consultas do reranker para um texto livre: o texto sem as frases de intenção + cada ideia separada.

    "quero pesquisar sistemas embarcados e internet das coisas" ->
        ["sistemas embarcados e internet das coisas", "sistemas embarcados", "internet das coisas"]
    O item fica com a MAIOR nota entre as consultas, então manter o texto inteiro nunca piora o resultado.
    """
    limpo = _INTENCAO.sub(" ", texto)
    limpo = re.sub(r"\s+", " ", limpo).strip(" ,.;:")
    if len(limpo) <= 2:
        limpo = texto.strip()
    partes = [p.strip(" ,.;:") for p in re.split(r"[;.,\n]|\s+e\s+|\s+ou\s+|\s+/\s+", limpo)]
    partes = [p for p in partes if len(p) > 2]
    return list(dict.fromkeys([limpo] + partes))


def consultas_rerank(topico: str, texto: str, modo: str | None = None) -> list[str]:
    """Consultas que o reranker compara com cada item, conforme config.RERANK_CONSULTA."""
    modo = modo or config.RERANK_CONSULTA
    nome = topico.lower() if topico in config.TOPICOS else None
    if modo == "texto":
        return [texto]
    if modo == "nome":
        return [nome or texto]
    if modo == "partes":
        partes = config.subtopicos_topico(topico)          # tópico estruturado: subtópicos escritos à mão
        if not partes and not nome:                         # texto livre do aluno
            return partes_texto_livre(texto)
        if not partes:                                      # tópico do catálogo só texto: quebra o texto
            partes = [p.strip(" ,:") for p in re.split(r"[;.]", texto)]
            partes = [p for p in partes if len(p) > 2]
            if nome:
                # partes automáticas podem ser curtas/ambíguas: "matching" -> "grafos: matching"
                # (subtópicos escritos à mão já fazem sentido sozinhos e não recebem prefixo)
                partes = [p if nome in p else f"{nome}: {p}" for p in partes]
        return list(dict.fromkeys(([nome] if nome else []) + (partes or [texto])))
    raise ValueError(f"RERANK_CONSULTA inválido: {modo!r}")


def calcular_scores(reranker, pares: list[tuple[str, str]]) -> None:
    """Garante a nota de cada par (consulta, texto) em _cache_scores.

    Ordem: memória -> cache em disco (pré-calculado) -> modelo (e salva no disco).
    """
    faltando = list(dict.fromkeys(p for p in pares if p not in _cache_scores))
    if not faltando:
        return

    disco = cache_disco()
    if disco is not None:
        chaves = {p: chave(p[0], p[1], RERANK_MAX_LENGTH) for p in faltando}
        achados = disco.buscar(list(chaves.values()))
        for p, k in chaves.items():
            if k in achados:
                _cache_scores[p] = achados[k]
        estatisticas["pares_do_disco"] += sum(1 for p in faltando if p in _cache_scores)
        faltando = [p for p in faltando if p not in _cache_scores]
        if not faltando:
            return

    if reranker is None:
        raise ValueError(f"{len(faltando)} par(es) sem nota no cache e nenhum reranker carregado")
    scores = reranker.compute_score(faltando, batch_size=16, max_length=RERANK_MAX_LENGTH, normalize=True)
    if scores is None:
        raise ValueError("O reranker não retornou scores")
    scores = [float(s) for s in np.atleast_1d(scores)]
    _cache_scores.update(zip(faltando, scores, strict=True))
    estatisticas["pares_calculados"] += len(faltando)
    if disco is not None:
        disco.salvar({chave(q, t, RERANK_MAX_LENGTH): s for (q, t), s in zip(faltando, scores)})


def pontuar_candidatos(reranker, consultas: str | list[str], candidatos: list[dict]) -> list[dict]:
    """Score de cada candidato = maior score entre as consultas (guarda qual consulta venceu)."""
    if not candidatos:
        return candidatos
    if isinstance(consultas, str):
        consultas = [consultas]
    textos = dict.fromkeys(str(c["texto"]) for c in candidatos)
    calcular_scores(reranker, [(q, t) for q in consultas for t in textos])
    for c in candidatos:
        t = str(c["texto"])
        melhor = max(consultas, key=lambda q: _cache_scores[(q, t)])
        c["rerank_bruto"] = _cache_scores[(melhor, t)]
        c["rerank_consulta"] = melhor
        c["rerank_score"] = c["rerank_bruto"] * c.get("peso_tipo", 1.0)
    return candidatos



def aplicar_corte(candidatos: list[dict], relativo: float | None = None,
                  manter_melhor: bool | None = None, por_tipo: bool | None = None,
                  absoluto: float | None = None) -> list[dict]:
    """Corte relativo ao melhor item (do mesmo tipo ou do tópico) + piso absoluto opcional
    + garantia opcional do melhor item por (professor, tipo).

    Marca em c["corte"] por que o item passou: "relativo" ou "melhor_do_tipo".
    O perfil do professor nunca é cortado.
    """
    relativo = config.MIN_RERANK_RELATIVO if relativo is None else relativo
    manter_melhor = config.MANTER_MELHOR_POR_TIPO if manter_melhor is None else manter_melhor
    por_tipo = config.CORTE_POR_TIPO if por_tipo is None else por_tipo
    absoluto = config.MIN_RERANK_ABSOLUTO if absoluto is None else absoluto

    itens = [c for c in candidatos if c["tipo"] != "professor"]
    if not itens:
        return candidatos
    if por_tipo:
        maximo: dict[str, float] = {}
        for c in itens:
            maximo[c["tipo"]] = max(maximo.get(c["tipo"], 0.0), c["rerank_bruto"])
        limites = {t: max(relativo * m, absoluto) for t, m in maximo.items()}
    else:
        geral = max(relativo * max(c["rerank_bruto"] for c in itens), absoluto)
        limites = {c["tipo"]: geral for c in itens}

    melhores = set()
    if manter_melhor:
        melhor_por_grupo: dict[tuple[str, str], dict] = {}
        for c in itens:
            chave = (c["professor_id"], c["tipo"])
            if chave not in melhor_por_grupo or c["rerank_bruto"] > melhor_por_grupo[chave]["rerank_bruto"]:
                melhor_por_grupo[chave] = c
        melhores = {id(c) for c in melhor_por_grupo.values()}

    resultado = []
    for c in candidatos:
        if c["tipo"] == "professor":
            resultado.append(c)
        elif c["rerank_bruto"] >= limites[c["tipo"]]:
            c["corte"] = "relativo"
            resultado.append(c)
        elif id(c) in melhores:
            c["corte"] = "melhor_do_tipo"
            resultado.append(c)
    return resultado


def _score_ponderado(itens: list[dict], n: int, decaimento: str | None = None):
    """Mesma média do pré-ranking (media_decaimento), sobre o rerank_score; None se não houver itens."""
    if not itens:
        return None
    return media_decaimento([i["rerank_score"] for i in itens], n, decaimento)


def rankear_professores(candidatos: list[dict]) -> list[dict]:
    por_prof: dict[str, dict] = {}

    for c in candidatos:
        d = por_prof.setdefault(c["professor_id"], {
            "professor_id": c["professor_id"],
            "professor_nome": None,
            "perfil": None,
            "itens": {tipo: [] for tipo in config.FONTES_ITENS},
        })
        d["professor_nome"] = d["professor_nome"] or c.get("professor_nome")

        if c["tipo"] == "professor":
            d["perfil"] = c["rerank_score"]
        else:
            d["itens"][c["tipo"]].append(c)

    for d in por_prof.values():
        componentes = [(config.PESO_PROFESSOR, d["perfil"])]
        componentes += [
            (cfg["peso_global"], _score_ponderado(d["itens"][tipo], cfg["n"], decaimento_da_fonte(tipo)))
            for tipo, cfg in config.FONTES_ITENS.items()
        ]
        d["rerank_score"] = (
            sum(w * (s or 0.0) for w, s in componentes) / sum(w for w, _ in componentes)
        )


    return sorted(por_prof.values(), key=lambda x: x["rerank_score"], reverse=True)

def unir_rerank(por_topico: dict[str, list[dict]]) -> list[dict]:
    """Média do rerank de cada professor entre os tópicos, guardando o detalhe de cada um."""
    unidos: dict[str, dict] = {}
    for topico, ranking in por_topico.items():
        for r in ranking:
            d = unidos.setdefault(r["professor_id"], {
                "professor_id": r["professor_id"],
                "professor_nome": r["professor_nome"],
                "scores_topicos": dict.fromkeys(por_topico, 0.0),
                "topicos": {},
            })
            d["scores_topicos"][topico] = r["rerank_score"]
            d["topicos"][topico] = r
    for d in unidos.values():
        d["rerank_score"] = sum(d["scores_topicos"].values()) / len(por_topico)
    return sorted(unidos.values(), key=lambda x: x["rerank_score"], reverse=True)
