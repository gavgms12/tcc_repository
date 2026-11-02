from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.modelo import embedar_consulta
from recuperacao.sistema_de_busca.database_vetores import busca_hibrida, filtro_ano
from .agregacao import combinar_scores, hits_para_df, score_top_n, scores_perfis, unir_topicos
from .reranking import criar_candidatos, pontuar_candidatos, rankear_professores, unir_rerank
from .diagnostico import explicar_pre_ranking, explicar_reranking, verificar_pesos_internos


class Recomendador:
    

    def __init__(self, client, modelo, reranker):
        self.client = client
        self.modelo = modelo
        self.reranker = reranker

    def _pre_rankear(self, texto: str, filtro, debug=False):
        """Busca híbrida em cada coleção e pré-ranking dos professores para um tópico."""
        emb = embedar_consulta(self.modelo, texto)
        pontos_prof = busca_hibrida(
            self.client, config.COLLECTION_PROFESSORES, emb, config.LIMIT_PROFESSORES
        )
        rels, scores_itens = {}, {}
        for tipo, cfg in config.FONTES_ITENS.items():
            pontos = busca_hibrida(
                self.client, cfg["collection"], emb, cfg["limit"],
                filtro=filtro if cfg.get("filtra_ano") else None,
            )
            if debug:
                verificar_pesos_internos(pontos, tipo)
            rels[tipo] = hits_para_df(pontos, tipo)
            scores_itens[tipo] = score_top_n(rels[tipo], f"{tipo}_score", cfg["n"])

        ranking = combinar_scores(scores_perfis(pontos_prof), scores_itens)
        if debug:
            explicar_pre_ranking(ranking)
        return ranking, rels

    def recomendar(self, topicos: dict[str, str], top_k: int = 10, ano_min=None, ano_max=None, debug=False) -> list[dict]:
        """topicos: {nome do tópico: texto usado na busca e no reranking}"""
        filtro = filtro_ano(ano_min, ano_max)

        # 1ª etapa: pré-ranking separado para cada tópico
        rankings, rels = {}, {}
        for topico, texto in topicos.items():
            rankings[topico], rels[topico] = self._pre_rankear(texto, filtro, debug)

       # 2ª etapa: união dos tópicos e corte nos melhores professores
        com_itens = {
            pid
            for rels_topico in rels.values()
            for rel in rels_topico.values()
            for pid in rel["professor_id"]
        }
        ranking = unir_topicos(rankings)
        ranking = ranking[ranking["professor_id"].isin(com_itens)].head(config.FINAL_PROFESSOR_K)
        scores_iniciais = ranking.set_index("professor_id")["score_final"].to_dict()

        # 3ª etapa: cada item é comparado com o tópico que o encontrou
        por_topico = {}
        for topico, texto in topicos.items():
            candidatos = criar_candidatos(self.client, ranking, rels[topico])
            candidatos = pontuar_candidatos(self.reranker, texto, candidatos)
            candidatos = [
                c for c in candidatos
                if c["tipo"] == "professor" or c["rerank_bruto"] >= config.MIN_RERANK
            ]
            por_topico[topico] = rankear_professores(candidatos)
            if debug:
                explicar_reranking(por_topico[topico])
        ranking_final = [
            r for r in unir_rerank(por_topico)
            if any(itens for det in r["topicos"].values() for itens in det["itens"].values())
        ]
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
                                {"id": i["item_id"], "titulo": i.get("titulo"), "subtipo": i.get("subtipo"), "score": i["rerank_score"]}
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
