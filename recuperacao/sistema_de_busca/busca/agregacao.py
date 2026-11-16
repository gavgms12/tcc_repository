import math

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


def pesos_decaimento(n: int, decaimento: str | None = None) -> list[float]:
    """Peso de cada posição (1ª, 2ª, ..., n-ésima) conforme o tipo de decaimento."""
    decaimento = decaimento or config.DECAIMENTO
    formulas = {
        "nenhum": lambda pos: 1.0,
        "linear": lambda pos: float(n - pos + 1),
        "log": lambda pos: 1.0 / math.log2(pos + 1),
        "harmonico": lambda pos: 1.0 / pos,
        "exponencial": lambda pos: 0.5 ** (pos - 1),
    }
    if decaimento not in formulas:
        raise ValueError(f"decaimento inválido: {decaimento!r} (use {list(formulas)})")
    return [formulas[decaimento](pos) for pos in range(1, n + 1)]


def media_decaimento(scores, n: int, decaimento: str | None = None) -> float:
    """Média ponderada dos n maiores scores; posições vazias contam como 0."""
    pesos = pesos_decaimento(n, decaimento)
    melhores = sorted(scores, reverse=True)[:n]
    return sum(s * p for s, p in zip(melhores, pesos)) / sum(pesos)


def decaimento_da_fonte(tipo: str) -> str:
    return config.FONTES_ITENS[tipo].get("decaimento", config.DECAIMENTO)


def score_top_n(rel: pd.DataFrame, coluna: str, n: int = 3, decaimento: str | None = None) -> pd.DataFrame:
    """Média dos n melhores itens de cada professor, com peso decrescente por posição (ver pesos_decaimento)."""
    if rel.empty:
        return pd.DataFrame({
            "professor_id": pd.Series(dtype="object"),
            coluna: pd.Series(dtype="float64"),
        })
    return (
        rel.groupby("professor_id")["score"]
           .apply(lambda s: media_decaimento(s.tolist(), n, decaimento))
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

MODOS_UNIAO = ("media", "max", "top_m", "decaimento")

def uniao_topicos(tabela: pd.DataFrame, modo: str | None = None) -> pd.Series:
    """Score final de cada linha (professor) a partir das colunas (tópicos), segundo o modo de união."""
    modo = modo or config.UNIAO_TOPICOS
    if modo not in MODOS_UNIAO:
        raise ValueError(f"UNIAO_TOPICOS inválido: {modo!r} (use {list(MODOS_UNIAO)})")
    valores = tabela.astype("float64").copy()
    if valores.empty:
        return pd.Series(0.0, index=tabela.index, dtype="float64")
    if config.NORMALIZAR_TOPICOS:
        valores = valores / valores.max().where(lambda m: m > 0, 1.0)
    if config.NOME_TEXTO_LIVRE in valores:
        valores[config.NOME_TEXTO_LIVRE] *= config.PESO_TEXTO_LIVRE

    n = valores.shape[1]
    # cada linha do melhor tópico para o pior
    ordenado = valores.apply(lambda linha: sorted(linha, reverse=True), axis=1, result_type="expand")
    if modo == "max":
        final = ordenado.iloc[:, 0]
    elif modo == "top_m":
        final = ordenado.iloc[:, :max(1, min(config.UNIAO_TOPICOS_M, n))].mean(axis=1)
    elif modo == "decaimento":
        pesos = pesos_decaimento(n, config.UNIAO_TOPICOS_DECAIMENTO)
        final = (ordenado * pesos).sum(axis=1) / sum(pesos)
    else:
        final = ordenado.mean(axis=1)
    return final.reindex(tabela.index).fillna(0.0)


def unir_topicos(rankings: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Junta os scores de cada professor entre os tópicos conforme config.UNIAO_TOPICOS; tópico ausente conta como 0.
    As colunas por tópico continuam com o score original; só o score_final muda."""
    tabela = pd.concat(
        {t: df.set_index("professor_id")["score_final"] for t, df in rankings.items()}, axis=1
    ).fillna(0.0)
    tabela["score_final"] = uniao_topicos(tabela)
    return (
        tabela.rename_axis("professor_id").reset_index()
              .sort_values("score_final", ascending=False).reset_index(drop=True)
    )
