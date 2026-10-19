from recuperacao.sistema_de_busca.config import FINAL_PROFESSOR_K
from recuperacao.sistema_de_busca.database_vetores import qdrant_id
from FlagEmbedding import FlagReranker
from config import RERANKER_MODEL, N_DISCIPLINAS, N_TRABALHOS
from collections import defaultdict
import numpy as np

def carregar_reranker():
    return FlagReranker(RERANKER_MODEL, use_fp16=True, normalize=True)
    
def buscar_payloads(client, collection, ids):
    ids = list(dict.fromkeys(str(i) for i in ids))   # remove duplicados, mantém ordem
    if not ids:
        return {}

    registros = client.retrieve(
        collection_name=collection,
        ids=[qdrant_id(i) for i in ids],
        with_payload=True,
        with_vectors=False,
    )
    return {str(r.payload["id"]): r.payload for r in registros}


def criar_candidatos_reranking(
    client,
    ranking,
    relacao_professor_trabalho,
    relacao_professor_disciplina,
    n_trabalhos=N_TRABALHOS,
    n_disciplinas=N_DISCIPLINAS,
):
    ids_prof = ranking["professor_id"].astype(str).tolist()

    # 1. Seleciona só os top-n itens de cada professor (ainda sem texto)
    def top_n(relacao, n):
        rel = relacao.copy()
        rel["professor_id"] = rel["professor_id"].astype(str)
        rel = rel[rel["professor_id"].isin(ids_prof)]
        return (
            rel.sort_values("score", ascending=False)
               .groupby("professor_id")
               .head(n)
        )

    trabalhos_sel = top_n(relacao_professor_trabalho, n_trabalhos)
    disciplinas_sel = top_n(relacao_professor_disciplina, n_disciplinas)

    # 2. Busca os textos no Qdrant, uma chamada por collection
    perfis = buscar_payloads(client, "professores", ids_prof)
    trabalhos = buscar_payloads(client, "iniciacao_cientifica", trabalhos_sel["objeto_id"])
    disciplinas = buscar_payloads(client, "disciplinas", disciplinas_sel["objeto_id"])

    trabalhos_por_prof = dict(tuple(trabalhos_sel.groupby("professor_id")))
    disciplinas_por_prof = dict(tuple(disciplinas_sel.groupby("professor_id")))

    # 3. Monta os candidatos
    def montar_itens(selecao, payloads, id_key, nome_key):
        itens = []
        if selecao is None:
            return itens
        for _, rel in selecao.iterrows():
            item = payloads.get(str(rel["objeto_id"]))
            if item is None:
                continue
            itens.append({
                id_key: str(rel["objeto_id"]),
                nome_key: item.get("titulo") or item.get("nome"),
                "texto": item.get("texto"),
                "score": rel["score"],
            })
        return itens

    candidatos = []

    for _, candidato in ranking.iterrows():
        professor_id = str(candidato["professor_id"])

        perfil = perfis.get(professor_id)
        if perfil is None:
            continue

        texto_perfil = perfil.get("texto") or ""

        trabalhos_rr = montar_itens(
            trabalhos_por_prof.get(professor_id), trabalhos, "trabalho_id", "titulo"
        )
        disciplinas_rr = montar_itens(
            disciplinas_por_prof.get(professor_id), disciplinas, "disciplina_id", "nome"
        )

        texto_reranking = texto_perfil

        textos_trabalhos = [t["texto"] for t in trabalhos_rr if t["texto"]]
        if textos_trabalhos:
            texto_reranking += "\n\nTrabalhos relevantes:\n" + "\n\n".join(textos_trabalhos)

        textos_disciplinas = [d["texto"] for d in disciplinas_rr if d["texto"]]
        if textos_disciplinas:
            texto_reranking += "\n\nDisciplinas relevantes:\n" + "\n\n".join(textos_disciplinas)

        candidatos.append({
            "professor_id": professor_id,
            "professor_nome": candidato["professor_nome"],

            "work_score": candidato["work_score"],
            "professor_score": candidato["professor_score"],
            "disciplina_score": candidato["disciplina_score"],
            "score_final": candidato["score_final"],

            "texto_perfil": texto_perfil,
            "texto_reranking": texto_reranking,

            "trabalhos_relevantes": trabalhos_rr,
            "disciplinas_relevantes": disciplinas_rr,
        })

    return candidatos

# fazendo o reraking e adicionando no arquivo dos conteudos

def reranking_dos_objetos_das_classes(aluno_texto, conteudo_reranking):
    reranker = carregar_reranker()
    
    pares = [
            (aluno_texto, candidato["texto"])
            for candidato in conteudo_reranking
            ]
    scores = reranker.compute_score(
                pares,
                normalize=True
             )
    
    scores = reranker.compute_score(pares, normalize=True)

    if scores is None:
        raise ValueError("O reranker não retornou scores")

    scores = [float(s) for s in np.atleast_1d(scores)]
            
def agrupar_por_professor(candidatos):
    professores = defaultdict(lambda: {
        "professor_id": None,
        "professor": None,
        "trabalhos_relevantes": [],
        "disciplinas_relevantes": []
    })

    for candidato in candidatos:
        professor_id = candidato["professor_id"]

        professores[professor_id]["professor_id"] = professor_id

        if candidato["tipo"] == "professor":
            professores[professor_id]["professor"] = candidato

        elif candidato["tipo"] == "trabalho":
            professores[professor_id]["trabalhos_relevantes"].append(candidato)

        elif candidato["tipo"] == "disciplina":
            professores[professor_id]["disciplinas_relevantes"].append(candidato)

    return dict(professores)

def calcular_score_final_professor(dados):
    componentes = []

    if dados["professor_rerank_score"] is not None:
        componentes.append(
            (0.20, dados["professor_rerank_score"])
        )

    if dados["work_rerank_score"] is not None:
        componentes.append(
            (0.50, dados["work_rerank_score"])
        )

    if dados["disciplina_rerank_score"] is not None:
        componentes.append(
            (0.30, dados["disciplina_rerank_score"])
        )

    if not componentes:
        return 0.0

    soma_pesos = sum(
        peso for peso, score in componentes
    )

    soma_scores = sum(
        peso * score
        for peso, score in componentes
    )

    return soma_scores / soma_pesos

def calcular_score_ponderado(itens, n=3):
    if not itens:
        return None

    itens_ordenados = sorted(
        itens,
        key=lambda x: x["rerank_score"],
        reverse=True
    )[:n]

    pesos = list(range(len(itens_ordenados), 0, -1))

    numerador = sum(
        item["rerank_score"] * peso
        for item, peso in zip(itens_ordenados, pesos)
    )

    denominador = sum(pesos)

    return numerador / denominador

def calcular_scores_professor(professores):
    for professor_id, dados in professores.items():

        # Score do perfil do professor
        if dados["professor"] is not None:
            dados["professor_rerank_score"] = (
                dados["professor"]["rerank_score"]
            )
        else:
            dados["professor_rerank_score"] = None

        # Score dos trabalhos
        dados["work_rerank_score"] = calcular_score_ponderado(
            dados["trabalhos_relevantes"],
            n=3
        )

        # Score das disciplinas
        dados["disciplina_rerank_score"] = calcular_score_ponderado(
            dados["disciplinas_relevantes"],
            n=3
        )

    return professores

def adicionar_dados_de_reranking_ao_inicial(scores_professores_reranking):
    for professor_id, dados in scores_professores_reranking.items():

        dados["rerank_score"] = (
            calcular_score_final_professor(dados)
        )
    
def ordernar_ranking(resultado_score, score="rerank_score"):
    return sorted(
            resultado_score.values(),
            key=lambda x: x[score],
            reverse=True
            )

def adicionar_nomes_professores(ranking_final, ranking):
    nomes = (
        ranking[
            ["professor_id", "professor_nome"]
        ]
        .drop_duplicates("professor_id")
        .set_index("professor_id")["professor_nome"]
        .to_dict()
    )

    for professor in ranking_final:
        professor["professor_nome"] = nomes.get(
            professor["professor_id"],
            professor["professor_id"]
        )

    return ranking_final

def imprimir_ranking(ranking_final, aluno_texto):

    print("CONSULTA DO ALUNO")
    print(aluno_texto)

    print("\n" + "=" * 100)
    print("RANKING COMPLETO")
    print("=" * 100)

    for i, professor in enumerate(ranking_final, start=1):

        print("=" * 100)

        print(
            f"{i}º - {professor['professor_nome']}"
        )

        print(
            f"Rerank score: "
            f"{professor['rerank_score']:.6f}"
        )

        print(
            f"Score inicial: "
            f"{professor['professor']['score_retrieval']:.6f}"
            if professor["professor"] is not None
            else "Score inicial: N/A"
        )

        # ==================================================
        # TRABALHOS
        # ==================================================

        print("\nTrabalhos relevantes:")

        trabalhos = professor["trabalhos_relevantes"]

        if not trabalhos:
            print("Nenhum trabalho relevante encontrado.")
        else:
            trabalhos = sorted(
                trabalhos,
                key=lambda x: x["rerank_score"],
                reverse=True
            )

            for j, trabalho in enumerate(trabalhos, start=1):

                titulo = trabalho.get("titulo")

                if not titulo:
                    titulo = trabalho["texto"].split("\n")[0]

                    if titulo.startswith("Título:"):
                        titulo = titulo.replace(
                            "Título:", "", 1
                        ).strip()

                print(f"\n  {j}. {titulo}")

                print(
                    f"     Score do trabalho: "
                    f"{trabalho['rerank_score']:.6f}"
                )

        # ==================================================
        # DISCIPLINAS
        # ==================================================

        print("\nDisciplinas relevantes:")

        disciplinas = professor["disciplinas_relevantes"]

        if not disciplinas:
            print("Nenhuma disciplina relevante encontrada.")
        else:
            disciplinas = sorted(
                disciplinas,
                key=lambda x: x["rerank_score"],
                reverse=True
            )

            for j, disciplina in enumerate(disciplinas, start=1):

                nome = disciplina.get("nome")

                if not nome:
                    nome = disciplina["texto"].split("\n")[0]

                    if nome.startswith("Nome:"):
                        nome = nome.replace(
                            "Nome:", "", 1
                        ).strip()

                print(f"\n  {j}. {nome}")

                print(
                    f"     Score da disciplina: "
                    f"{disciplina['rerank_score']:.6f}"
                )