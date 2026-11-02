import numpy as np
import pandas as pd
from FlagEmbedding import FlagReranker

from recuperacao.sistema_de_busca import config
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


def pontuar_candidatos(reranker, texto_aluno: str, candidatos: list[dict]) -> list[dict]:
    if not candidatos:
        return candidatos
    textos = dict.fromkeys(str(c["texto"]) for c in candidatos)
    faltando = [t for t in textos if (texto_aluno, t) not in _cache_scores]
    if faltando:
        pares = [(texto_aluno, t) for t in faltando]
        scores = reranker.compute_score(pares, batch_size=16, max_length=512, normalize=True)
        if scores is None:
            raise ValueError("O reranker não retornou scores")
        scores = [float(s) for s in np.atleast_1d(scores)]
        _cache_scores.update(
            ((texto_aluno, t), s) for t, s in zip(faltando, scores, strict=True)
        )
    for c in candidatos:
        c["rerank_bruto"] = _cache_scores[(texto_aluno, str(c["texto"]))]
        c["rerank_score"] = c["rerank_bruto"] * c.get("peso_tipo", 1.0)
    return candidatos



def _score_ponderado(itens: list[dict], n: int):
    """Média ponderada 3-2-1 dos n melhores; posições vazias contam como 0 (None se não houver itens)."""
    if not itens:
        return None
    melhores = sorted(itens, key=lambda x: x["rerank_score"], reverse=True)[:n]
    pesos = range(n, 0, -1)
    return sum(i["rerank_score"] * p for i, p in zip(melhores, pesos)) / sum(pesos)


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
            (cfg["peso_global"], _score_ponderado(d["itens"][tipo], cfg["n"]))
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
