import pandas as pd
from recuperacao.sistema_de_busca import config

def hits_para_df(pontos, fonte: str) -> pd.DataFrame:
    """Uma linha por par (professor, item). O score já sai multiplicado pelo peso interno."""
    linhas = [
        {
            "professor_id": str(pid),
            "objeto_id": str(p.payload["id"]),
            "score": p.score * config.peso_interno(fonte, p.payload),
        }
        for p in pontos
        for pid in p.payload.get("professor_ids", [])
    ]
    df = pd.DataFrame(linhas, columns=["professor_id", "objeto_id", "score"])
    df["score"] = df["score"].astype("float64")
    return df

def score_top_n(rel: pd.DataFrame, coluna: str, n: int = 3) -> pd.DataFrame:
    """Média dos n melhores itens de cada professor."""
    if rel.empty:
        return pd.DataFrame({
            "professor_id": pd.Series(dtype="object"),
            coluna: pd.Series(dtype="float64"),
        })
    return (
        rel.sort_values("score", ascending=False)
           .groupby("professor_id").head(n)
           .groupby("professor_id")["score"].sum()
           .div(n)
           .reset_index()
           .rename(columns={"score": coluna})
    )


def scores_perfis(pontos) -> pd.DataFrame:
    df = pd.DataFrame(
        [{"professor_id": str(p.payload["id"]), "professor_score": p.score} for p in pontos],
        columns=["professor_id", "professor_score"],
    )
    df["professor_score"] = df["professor_score"].astype("float64")
    return df


def combinar_scores(scores_perfil: pd.DataFrame, scores_itens: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """scores_itens: {tipo: DataFrame[professor_id, '<tipo>_score']}"""
    df = scores_perfil
    for s in scores_itens.values():
        df = df.merge(s, on="professor_id", how="outer")

    pesos = {"professor_score": config.PESO_PROFESSOR}
    pesos.update({
        f"{tipo}_score": cfg["peso_global"]
        for tipo, cfg in config.FONTES_ITENS.items()
    })

    for coluna in pesos:
        if coluna not in df:
            df[coluna] = float("nan")
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")

    # média ponderada só com os componentes que existem para cada professor
    numerador = sum(df[c].fillna(0.0) * w for c, w in pesos.items())
    df["score_final"] = numerador / sum(pesos.values())


    return df.sort_values("score_final", ascending=False).reset_index(drop=True)

def unir_topicos(rankings: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Média dos scores de cada professor entre os tópicos; tópico ausente conta como 0."""
    tabela = pd.concat(
        {t: df.set_index("professor_id")["score_final"] for t, df in rankings.items()}, axis=1
    ).fillna(0.0)
    tabela["score_final"] = tabela.mean(axis=1)
    return (
        tabela.rename_axis("professor_id").reset_index()
              .sort_values("score_final", ascending=False).reset_index(drop=True)
    )
