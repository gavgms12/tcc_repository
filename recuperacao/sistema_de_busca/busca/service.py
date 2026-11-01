from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.modelo import embedar_consulta
from recuperacao.sistema_de_busca.database_vetores import busca_hibrida

from .agregacao import combinar_scores, hits_para_df, score_top_n, scores_perfis
from .reranking import criar_candidatos, pontuar_candidatos, rankear_professores


class Recomendador:
    def __init__(self, client, modelo, reranker):
        self.client = client
        self.modelo = modelo
        self.reranker = reranker

    def recomendar(self, texto_aluno: str, top_k: int = 10) -> list[dict]:
        emb = embedar_consulta(self.modelo, texto_aluno)

        # 1ª etapa: busca híbrida em cada coleção
        pontos_prof = busca_hibrida(
            self.client, config.COLLECTION_PROFESSORES, emb, config.LIMIT_PROFESSORES
        )

        rels, scores_itens = {}, {}
        for tipo, cfg in config.FONTES_ITENS.items():
            pontos = busca_hibrida(self.client, cfg["collection"], emb, cfg["limit"])
            rels[tipo] = hits_para_df(pontos)
            scores_itens[tipo] = score_top_n(rels[tipo], f"{tipo}_score", cfg["n"])

        # 2ª etapa: pré-ranking com pesos e corte nos melhores professores
        ranking = combinar_scores(scores_perfis(pontos_prof), scores_itens).head(
            config.FINAL_PROFESSOR_K
        )
        scores_iniciais = ranking.set_index("professor_id")["score_final"].to_dict()

        # 3ª etapa: reranking com os textos
        candidatos = criar_candidatos(self.client, ranking, rels)
        candidatos = pontuar_candidatos(self.reranker, texto_aluno, candidatos)

        return self._formatar(rankear_professores(candidatos)[:top_k], scores_iniciais)

    @staticmethod
    def _formatar(ranking: list[dict], scores_iniciais: dict) -> list[dict]:
        return [
            {
                "professor_id": r["professor_id"],
                "nome": r["professor_nome"],
                "score": r["rerank_score"],
                "score_inicial": scores_iniciais.get(r["professor_id"]),
                "score_perfil": r["perfil"],
                "itens": {
                    tipo: [
                        {"id": i["item_id"], "titulo": i.get("titulo"), "score": i["rerank_score"]}
                        for i in sorted(lista, key=lambda x: x["rerank_score"], reverse=True)
                    ]
                    for tipo, lista in r["itens"].items()
                },
            }
            for r in ranking
        ]