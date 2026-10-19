import pandas as pd
from recuperacao.sistema_de_busca.config import PESO_DISCIPLINAS,PESO_IC,PESO_PERFIL

# ligar conteúdo com o professor pelo id
def relacionar_dados(professores, relacionado = ""):
    relacoes = []

    for professor in professores:
        siape = professor.get("siape")
        nome = professor.get("nome")

        trabalhos = professor.get(relacionado, [])

        for trabalho in trabalhos:
            relacoes.append({
                "professor_id": siape,
                "nome": nome,
                "objeto_id": trabalho
            })
            
    return pd.DataFrame(relacoes)
# utilizando dataframe para realizarmos o merge
def criar_dataframe_scores_dos_objetos(resultados_trabalhos):
    resultados = []

    for point in resultados_trabalhos:
        resultados.append({
            "objeto_id": str(point.payload["id"]),
            "score": point.score
        })

    return pd.DataFrame(resultados)

def criar_dataframe_resultados_perfil_professores(resultados):
    dados = []

    for ponto in resultados:
        if not ponto.payload:
            continue

        dados.append({
            "professor_id": ponto.payload["id"],
            "professor_nome": ponto.payload["nome"],
            "professor_score": ponto.score
        })

    return pd.DataFrame(dados)

def associar_scores_a_professores(resultados_trabalhos,relacao):
    objetos_df = criar_dataframe_scores_dos_objetos(
        resultados_trabalhos
    )

    resultado = relacao.merge(
        objetos_df,
        on="objeto_id",
        how="inner"
    )

    return resultado.sort_values(
        by="score",
        ascending=False
    ).reset_index(drop=True)

# calculo dos scores das classes em geral
def calcular_score_iniciacao_cientifica(resultado):
    scores = (
        resultado
        .sort_values(
            by=["professor_id", "score"],
            ascending=[True, False]
        )
        .groupby("professor_id")
        .head(3)
        .groupby("professor_id")["score"]
        .mean()
        .reset_index()
        .rename(columns={
            "score": "ic_score"
        })
    )

    return scores


def calcular_score_disciplinas(resultado):
    scores = (
        resultado
        .sort_values(
            by=["professor_id", "score"],
            ascending=[True, False]
        )
        .groupby("professor_id")
        .head(3)
        .groupby("professor_id")["score"]
        .mean()
        .reset_index()
        .rename(columns={
            "score": "disciplina_score"
        })
    )

    return scores

def combinar_scores(
    scores_trabalhos,
    scores_professores,
    scores_disciplinas,
    peso_iniciacao_cientifica=PESO_IC,
    peso_professor=PESO_PERFIL,
    peso_disciplinas=PESO_DISCIPLINAS
):
    resultado = (
        scores_trabalhos
        .merge(
            scores_professores,
            on="professor_id",
            how="outer"
        )
        .merge(
            scores_disciplinas,
            on="professor_id",
            how="outer"
        )
    )

    resultado["ic_score"] = (
        resultado["ic_score"].fillna(0)
    )

    resultado["professor_score"] = (
        resultado["professor_score"].fillna(0)
    )

    resultado["disciplina_score"] = (
        resultado["disciplina_score"].fillna(0)
    )

    resultado["score_final"] = (
        peso_iniciacao_cientifica * resultado["ic_score"]
        +
        peso_professor * resultado["professor_score"]
        +
        peso_disciplinas * resultado["disciplina_score"]
    )

    return resultado.sort_values(
        "score_final",
        ascending=False
    )
    