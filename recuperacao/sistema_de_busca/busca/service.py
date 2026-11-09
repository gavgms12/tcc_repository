import time
from contextlib import contextmanager

import pandas as pd

from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.modelo import embedar_consultas
from recuperacao.sistema_de_busca.database_vetores import busca_hibrida, buscar_payloads_varios, em_paralelo, filtro_ano
from .agregacao import combinar_scores, decaimento_da_fonte, hits_para_df, score_top_n, scores_perfis, unir_topicos
from .reranking import (aplicar_corte, consultas_rerank, criar_candidatos, ids_candidatos, pontuar_candidatos,
                        rankear_professores, unir_rerank)
from .diagnostico import explicar_pre_ranking, explicar_reranking, verificar_pesos_internos


class Recomendador:
    

    def __init__(self, client, modelo, reranker):
        self.client = client
        self.modelo = modelo
        self.reranker = reranker
        self.tempos: dict[str, float] = {}   # segundos da última chamada de recomendar()/pre_ranking()
        self.professores_cortados: list[tuple[str, float]] = []   # (nome, score) cortados na última recomendar()

    @contextmanager
    def _medir(self, etapa: str):
        """Soma em self.tempos[etapa] o tempo do bloco (acumula entre tópicos)."""
        inicio = time.perf_counter()
        try:
            yield
        finally:
            self.tempos[etapa] = self.tempos.get(etapa, 0.0) + time.perf_counter() - inicio

    def _buscar(self, topicos: dict[str, str], filtro) -> dict[tuple[str, str], list]:
        """Embedding de todos os tópicos (um lote só) e busca híbrida de cada (tópico, coleção) em paralelo.

        Retorna {(tópico, "professor" ou tipo): pontos}.
        """
        with self._medir("embedding"):
            embs = dict(zip(topicos, embedar_consultas(self.modelo, list(topicos.values()))))
        tarefas = {}
        for topico, emb in embs.items():
            tarefas[(topico, "professor")] = (
                lambda emb=emb: busca_hibrida(self.client, config.COLLECTION_PROFESSORES, emb, config.LIMIT_PROFESSORES)
            )
            for tipo, cfg in config.FONTES_ITENS.items():
                tarefas[(topico, tipo)] = (
                    lambda emb=emb, cfg=cfg: busca_hibrida(
                        self.client, cfg["collection"], emb, cfg["limit"],
                        filtro=filtro if cfg.get("filtra_ano") else None,
                    )
                )
        with self._medir("qdrant"):
            return em_paralelo(tarefas)

    def _pre_rankear(self, topico: str, resultados: dict[tuple[str, str], list], debug=False):
        """Pré-ranking dos professores para um tópico, a partir dos resultados de _buscar."""
        pontos_prof = resultados[(topico, "professor")]
        rels, scores_itens = {}, {}
        for tipo in config.FONTES_ITENS:
            pontos = resultados[(topico, tipo)]
            if debug:
                verificar_pesos_internos(pontos, tipo)
            rels[tipo] = hits_para_df(pontos, tipo)

        for tipo, cfg in config.FONTES_ITENS.items():
            scores_itens[tipo] = score_top_n(rels[tipo], f"{tipo}_score", cfg["n"], decaimento_da_fonte(tipo))

        ranking = combinar_scores(scores_perfis(pontos_prof), scores_itens)
        if debug:
            explicar_pre_ranking(ranking)
        return ranking, rels

    def _ranking_inicial(self, topicos: dict[str, str], ano_min=None, ano_max=None, debug=False):
        """1ª e 2ª etapas: pré-ranking por tópico, união dos tópicos e corte nos melhores professores."""
        filtro = filtro_ano(ano_min, ano_max)

        # 1ª etapa: pré-ranking separado para cada tópico
        rankings, rels = {}, {}
        with self._medir("busca"):
            resultados = self._buscar(topicos, filtro)
            for topico in topicos:
                rankings[topico], rels[topico] = self._pre_rankear(topico, resultados, debug)

        # 2ª etapa: união dos tópicos e corte nos melhores professores
        com_itens = {
            pid
            for rels_topico in rels.values()
            for rel in rels_topico.values()
            for pid in rel["professor_id"]
        }
        ranking = unir_topicos(rankings)
        ranking = ranking[ranking["professor_id"].isin(com_itens)].head(config.FINAL_PROFESSOR_K)
        return ranking, rankings, rels

    def pre_ranking(self, topicos: dict[str, str], top_k: int = 10, ano_min=None, ano_max=None,
                    n_itens: int = 3, debug=False) -> list[dict]:
        """Ranking só com os scores da busca híbrida (sem reranking), no mesmo formato de recomendar()."""
        self.tempos = {}
        inicio = time.perf_counter()
        ranking, rankings, rels = self._ranking_inicial(topicos, ano_min, ano_max, debug)
        ranking = ranking.head(top_k)
        ids = ranking["professor_id"].tolist()

        # melhores itens de cada professor, por tópico e tipo, com o score da busca
        selecoes = {}
        for tipo in config.FONTES_ITENS:
            for topico in topicos:
                rel = rels[topico][tipo]
                selecoes[(topico, tipo)] = (
                    rel[rel["professor_id"].isin(ids)]
                    .sort_values("score", ascending=False)
                    .groupby("professor_id").head(n_itens)
                )

        # payloads de todas as coleções de uma vez, em paralelo
        pedidos = {"professor": (config.COLLECTION_PROFESSORES, ids)}
        for tipo, cfg in config.FONTES_ITENS.items():
            ids_itens = list({i for t in topicos for i in selecoes[(t, tipo)]["objeto_id"]})
            pedidos[tipo] = (cfg["collection"], ids_itens)
        por_colecao = buscar_payloads_varios(self.client, dict(pedidos.values()))
        payloads = {tipo: por_colecao.get(colecao, {}) for tipo, (colecao, _) in pedidos.items()}
        perfis = payloads.pop("professor")

        componentes = {
            topico: df.set_index("professor_id").to_dict("index") for topico, df in rankings.items()
        }

        def _valor(v):
            return None if pd.isna(v) else float(v)

        resultado = []
        for _, linha in ranking.iterrows():
            pid = linha["professor_id"]
            detalhe_topicos = {}
            for topico in topicos:
                comp = componentes[topico].get(pid, {})
                itens = {}
                for tipo in config.FONTES_ITENS:
                    sel = selecoes[(topico, tipo)]
                    itens[tipo] = [
                        {
                            "id": r["objeto_id"],
                            "titulo": (payloads[tipo].get(r["objeto_id"]) or {}).get("titulo")
                                      or (payloads[tipo].get(r["objeto_id"]) or {}).get("nome"),
                            "subtipo": (payloads[tipo].get(r["objeto_id"]) or {}).get("tipo"),
                            "codigo": (payloads[tipo].get(r["objeto_id"]) or {}).get("codigo"),
                            "score": float(r["score"]),
                        }
                        for _, r in sel[sel["professor_id"] == pid].iterrows()
                    ]
                detalhe_topicos[topico] = {
                    "score": _valor(comp.get("score_final")),
                    "componentes": {
                        "perfil": _valor(comp.get("professor_score")),
                        **{tipo: _valor(comp.get(f"{tipo}_score")) for tipo in config.FONTES_ITENS},
                    },
                    "itens": itens,
                }
            resultado.append({
                "professor_id": pid,
                "nome": (perfis.get(pid) or {}).get("nome"),
                "score": float(linha["score_final"]),
                "scores_topicos": {t: float(linha[t]) for t in topicos},
                "topicos": detalhe_topicos,
            })
        self.tempos["total"] = time.perf_counter() - inicio
        return resultado

    def recomendar(self, topicos: dict[str, str], top_k: int = 10, ano_min=None, ano_max=None, debug=False) -> list[dict]:
        """topicos: {nome do tópico: texto usado na busca e no reranking}"""
        self.tempos = {}
        inicio = time.perf_counter()
        ranking, _, rels = self._ranking_inicial(topicos, ano_min, ano_max, debug)
        scores_iniciais = ranking.set_index("professor_id")["score_final"].to_dict()

        # 3ª etapa: cada item é comparado com o tópico que o encontrou
        por_topico = {}
        with self._medir("reranking"):
            with self._medir("candidatos"):   # payloads de todos os tópicos de uma vez, em paralelo
                payloads = buscar_payloads_varios(self.client, ids_candidatos(ranking, rels))
            for topico, texto in topicos.items():
                with self._medir("candidatos"):
                    candidatos = criar_candidatos(self.client, ranking, rels[topico], payloads)
                with self._medir("modelo_reranker"):
                    candidatos = pontuar_candidatos(self.reranker, consultas_rerank(topico, texto), candidatos)
                candidatos = aplicar_corte(candidatos)
                por_topico[topico] = rankear_professores(candidatos)
                if debug:
                    explicar_reranking(por_topico[topico])
            ranking_final = [
                r for r in unir_rerank(por_topico)
                if any(itens for det in r["topicos"].values() for itens in det["itens"].values())
            ]
            # corte de professores relativo ao 1º colocado
            if ranking_final:
                limite = config.MIN_SCORE_PROFESSOR_RELATIVO * ranking_final[0]["rerank_score"]
                self.professores_cortados = [
                    (r["professor_nome"] or r["professor_id"], r["rerank_score"])
                    for r in ranking_final[:top_k] if r["rerank_score"] < limite
                ]
                ranking_final = [r for r in ranking_final if r["rerank_score"] >= limite]
            else:
                self.professores_cortados = []
        self.tempos["total"] = time.perf_counter() - inicio
        return self._formatar(ranking_final[:top_k], scores_iniciais)


    @staticmethod
    def _formatar(ranking: list[dict], scores_iniciais: dict) -> list[dict]:
        return [
            {
                "professor_id": r["professor_id"],
                "nome": r["professor_nome"],
                "score": r["rerank_score"],
                "score_inicial": scores_iniciais.get(r["professor_id"]),
                "scores_topicos": r["scores_topicos"],
                "topicos": {
                    topico: {
                        "score_perfil": det["perfil"],
                        "itens": {
                            tipo: [
                                {"id": i["item_id"], "titulo": i.get("titulo"), "subtipo": i.get("subtipo"), "codigo": i.get("codigo"),
                                 "score": i["rerank_score"], "corte": i.get("corte"),
                                 "consulta": i.get("rerank_consulta")}
                                for i in sorted(lista, key=lambda x: x["rerank_score"], reverse=True)
                            ]
                            for tipo, lista in det["itens"].items()
                        },
                    }
                    for topico, det in r["topicos"].items()
                },
            }
            for r in ranking
        ]
