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
                "peso_tipo": config.peso_do_item(item),
            })

    return candidatos


def pontuar_candidatos(reranker, texto_aluno: str, candidatos: list[dict]) -> list[dict]:
    if not candidatos:
        return candidatos
    pares = [(texto_aluno, str(c["texto"])) for c in candidatos]
    scores = reranker.compute_score(pares, normalize=True)
    if scores is None:
        raise ValueError("O reranker não retornou scores")
    scores = [float(s) for s in np.atleast_1d(scores)]
    for c, s in zip(candidatos, scores, strict=True):
        c["rerank_bruto"] = s
        c["rerank_score"] = s * c.get("peso_tipo", 1.0)
    return candidatos


def _score_ponderado(itens: list[dict], n: int):
    """Média ponderada 3-2-1 dos n melhores (None se não houver itens)."""
    if not itens:
        return None
    melhores = sorted(itens, key=lambda x: x["rerank_score"], reverse=True)[:n]
    pesos = range(len(melhores), 0, -1)
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
            (cfg["peso"], _score_ponderado(d["itens"][tipo], cfg["n"]))
            for tipo, cfg in config.FONTES_ITENS.items()
        ]
        validos = [(w, s) for w, s in componentes if s is not None]
        d["rerank_score"] = (
            sum(w * s for w, s in validos) / sum(w for w, _ in validos) if validos else 0.0
        )

    return sorted(por_prof.values(), key=lambda x: x["rerank_score"], reverse=True)