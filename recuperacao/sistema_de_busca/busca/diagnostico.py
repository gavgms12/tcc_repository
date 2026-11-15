import pandas as pd

from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.busca.agregacao import decaimento_da_fonte
from recuperacao.sistema_de_busca.busca.reranking import _score_ponderado


def verificar_config() -> None:
    pesos = {"professor": config.PESO_PROFESSOR}
    pesos.update({t: c["peso_global"] for t, c in config.FONTES_ITENS.items()})

    print("Pesos globais:")
    for nome, peso in pesos.items():
        print(f"  {nome:<12} {peso:.2f}")
    print(f"  soma = {sum(pesos.values()):.2f}")

    print("\nPesos internos:")
    for tipo, cfg in config.FONTES_ITENS.items():
        print(f"  {tipo}: {cfg.get('pesos_internos')}")


def verificar_pesos_internos(pontos, fonte: str, n: int = 8) -> None:
    """Mostra score bruto, multiplicador e score ponderado dos primeiros resultados."""
    print(f"\n[{fonte}] bruto x multiplicador = ponderado")
    for p in pontos[:n]:
        tipo = p.payload.get("tipo")
        mult = config.peso_interno(fonte, p.payload)
        nome = str(p.payload.get("titulo") or p.payload.get("nome"))[:45]
        print(f"  {nome:<45} tipo={tipo!s:<18} {p.score:.5f} x {mult:.2f} = {p.score * mult:.5f}")

    tipos_config = set(config.FONTES_ITENS[fonte].get("pesos_internos", {})) - {"padrao"}
    if tipos_config and all(p.payload.get("tipo") is None for p in pontos):
        print(f"  ATENÇÃO: '{fonte}' tem pesos internos, mas nenhum resultado trouxe 'tipo'. "
              "Todos caíram em 'padrao'. Confira os campos pedidos em busca_hibrida.")


def explicar_pre_ranking(ranking: pd.DataFrame, k: int = 5) -> None:
    pesos = {"professor_score": config.PESO_PROFESSOR}
    pesos.update({f"{t}_score": c["peso_global"] for t, c in config.FONTES_ITENS.items()})

    for _, linha in ranking.head(k).iterrows():
        print(f"\n=== 1ª etapa: professor {linha['professor_id']} ===")
        num = den = 0.0
        for coluna, peso in pesos.items():
            valor = linha.get(coluna)
            if pd.notna(valor):
                num += valor * peso
                den = sum(pesos.values())
                print(f"  {coluna:<22} score={valor:.5f} peso={peso:.2f} contribuição={valor * peso:.5f}")
            else:
                print(f"  {coluna:<22} ausente (fora da média)")
        calculado = num / den
        status = "OK" if abs(calculado - linha["score_final"]) < 1e-9 else "DIVERGE"
        print(f"  {num:.5f} / {den:.2f} = {calculado:.5f} | score_final={linha['score_final']:.5f} [{status}]")


def explicar_reranking(ranking_final: list[dict], k: int = 5) -> None:
    for d in ranking_final[:k]:
        print(f"\n=== 3ª etapa: {d['professor_nome'] or d['professor_id']} ===")
        num = den = 0.0

        if d["perfil"] is not None:
            num += config.PESO_PROFESSOR * d["perfil"]
            den += config.PESO_PROFESSOR
            print(f"  perfil: {d['perfil']:.5f} (peso {config.PESO_PROFESSOR:.2f})")

        for tipo, cfg in config.FONTES_ITENS.items():
            itens = sorted(d["itens"][tipo], key=lambda x: x["rerank_score"], reverse=True)
            comp = _score_ponderado(itens, cfg["n"], decaimento_da_fonte(tipo))
            if comp is None:
                print(f"  {tipo}: sem itens (fora da média)")
                continue
            print(f"  {tipo}: média ({decaimento_da_fonte(tipo)}, n={cfg['n']}) = {comp:.5f} (peso {cfg['peso_global']:.2f})")
            for i in itens[:cfg["n"]]:
                print(f"      {str(i.get('titulo'))[:50]:<50} "
                      f"bruto={i['rerank_bruto']:.4f} x {i['peso_tipo']:.2f} = {i['rerank_score']:.4f}"
                      f"  [consulta: {str(i.get('rerank_consulta'))[:40]}] [corte: {i.get('corte')}]")
            num += cfg["peso_global"] * comp
            den = config.PESO_PROFESSOR + sum(c["peso_global"] for c in config.FONTES_ITENS.values())


        calculado = num / den
        status = "OK" if abs(calculado - d["rerank_score"]) < 1e-9 else "DIVERGE"
        print(f"  {num:.5f} / {den:.2f} = {calculado:.5f} | rerank_score={d['rerank_score']:.5f} [{status}]")