import re

import numpy as np
import pandas as pd
from FlagEmbedding import FlagReranker

from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.busca.agregacao import decaimento_da_fonte, media_decaimento
from recuperacao.sistema_de_busca.database_vetores import buscar_payloads


def carregar_reranker() -> FlagReranker:
    return FlagReranker(config.RERANKER_MODEL, use_fp16=True, normalize=True)


def _top_n(rel: pd.DataFrame, ids_prof: list[str], n: int) -> pd.DataFrame:
    rel = rel[rel["professor_id"].isin(ids_prof)]
    return rel.sort_values("score", ascending=False).groupby("professor_id").head(n)


def criar_candidatos(client, ranking: pd.DataFrame, rels: dict[str, pd.DataFrame]) -> list[dict]:
    """Lista plana: perfil + melhores itens de cada tipo, cada um com seu texto."""
    ids_prof = ranking["professor_id"].tolist()
    perfis = buscar_payloads(client, config.COLLECTION_PROFESSORES, ids_prof)
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
        selecao = _top_n(rels[tipo], ids_prof, cfg["n"])
        payloads = buscar_payloads(client, cfg["collection"], selecao["objeto_id"])

        for _, rel in selecao.iterrows():
            item = payloads.get(rel["objeto_id"])
            pid = rel["professor_id"]
            if pid not in perfis or not item or not item.get("texto"):
                continue
            candidatos.append({
                "professor_id": pid, "professor_nome": nomes.get(pid),
                "tipo": tipo, "item_id": rel["objeto_id"], "texto": item["texto"],
                "titulo": item.get("titulo") or item.get("nome"),
                "subtipo": item.get("tipo"),                       # livro, artigo_periodico, pesquisa...
                "peso_tipo": config.peso_interno(tipo, item),
            })

    return candidatos


_cache_scores: dict[tuple[str, str], float] = {}


def consultas_rerank(topico: str, texto: str, modo: str | None = None) -> list[str]:
    """Consultas que o reranker compara com cada item, conforme config.RERANK_CONSULTA."""
    modo = modo or config.RERANK_CONSULTA
    nome = topico.lower() if topico in config.TOPICOS else None
    if modo == "texto":
        return [texto]
    if modo == "nome":
        return [nome or texto]
    if modo == "partes":
        partes = [p.strip(" ,:") for p in re.split(r"[;.]", texto)]
        partes = [p for p in partes if len(p) > 2]
        return list(dict.fromkeys(([nome] if nome else []) + (partes or [texto])))
    raise ValueError(f"RERANK_CONSULTA inválido: {modo!r}")


def pontuar_candidatos(reranker, consultas: str | list[str], candidatos: list[dict]) -> list[dict]:
    """Score de cada candidato = maior score entre as consultas (guarda qual consulta venceu)."""
    if not candidatos:
        return candidatos
    if isinstance(consultas, str):
        consultas = [consultas]
    textos = dict.fromkeys(str(c["texto"]) for c in candidatos)
    faltando = [(q, t) for q in consultas for t in textos if (q, t) not in _cache_scores]
    if faltando:
        scores = reranker.compute_score(faltando, batch_size=16, max_length=512, normalize=True)
        if scores is None:
            raise ValueError("O reranker não retornou scores")
        scores = [float(s) for s in np.atleast_1d(scores)]
        _cache_scores.update(zip(faltando, scores, strict=True))
    for c in candidatos:
        t = str(c["texto"])
        melhor = max(consultas, key=lambda q: _cache_scores[(q, t)])
        c["rerank_bruto"] = _cache_scores[(melhor, t)]
        c["rerank_consulta"] = melhor
        c["rerank_score"] = c["rerank_bruto"] * c.get("peso_tipo", 1.0)
    return candidatos



def aplicar_corte(candidatos: list[dict], relativo: float | None = None,
                  manter_melhor: bool | None = None) -> list[dict]:
    """Corte relativo ao melhor item do tópico + garantia do melhor item por (professor, tipo).

    Marca em c["corte"] por que o item passou: "relativo" ou "melhor_do_tipo".
    O perfil do professor nunca é cortado.
    """
    relativo = config.MIN_RERANK_RELATIVO if relativo is None else relativo
    manter_melhor = config.MANTER_MELHOR_POR_TIPO if manter_melhor is None else manter_melhor

    itens = [c for c in candidatos if c["tipo"] != "professor"]
    if not itens:
        return candidatos
    limite = relativo * max(c["rerank_bruto"] for c in itens)

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
        elif c["rerank_bruto"] >= limite:
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
