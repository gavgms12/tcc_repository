"""Pré-calcula as notas do reranker para (tópico do catálogo, item) e salva no cache em disco.

Por padrão só calcula os itens que a busca híbrida de cada tópico retorna (os únicos que podem
virar candidatos). --todos calcula todos os itens de todas as coleções.

Rodar depois da indexação (ou quando mudar tópicos, RERANK_CONSULTA ou o modelo):
    python -m recuperacao.sistema_de_busca.indexacao.prerankear --estimar
    python -m recuperacao.sistema_de_busca.indexacao.prerankear
    python -m recuperacao.sistema_de_busca.indexacao.prerankear --topicos Grafos "Matemática Discreta" --modo partes
    python -m recuperacao.sistema_de_busca.indexacao.prerankear --todos --tipos professor

É retomável: pares já salvos são pulados, então dá para interromper (Ctrl+C) e rodar de novo.
Itens que só aparecem com filtro de ano são calculados na hora da consulta e também ficam salvos.
"""
import argparse
import time

from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.busca import reranking
from recuperacao.sistema_de_busca.busca.cache_rerank import cache_disco, chave
from recuperacao.sistema_de_busca.database_vetores import buscar_payloads, busca_hibrida, conectar_Qdrant
from recuperacao.sistema_de_busca.modelo import carregar_modelo, embedar_consulta

COLECOES = {"professor": config.COLLECTION_PROFESSORES,
            **{tipo: cfg["collection"] for tipo, cfg in config.FONTES_ITENS.items()}}
LIMITES = {"professor": config.LIMIT_PROFESSORES,
           **{tipo: cfg["limit"] for tipo, cfg in config.FONTES_ITENS.items()}}


def textos_da_colecao(client, colecao: str) -> list[str]:
    """Todos os textos de uma coleção."""
    if not client.collection_exists(colecao):
        return []
    textos, offset = [], None
    while True:
        pontos, offset = client.scroll(colecao, limit=500, offset=offset,
                                       with_payload=["texto"], with_vectors=False)
        textos += [str(p.payload["texto"]) for p in pontos if p.payload.get("texto")]
        if offset is None:
            return list(dict.fromkeys(textos))


def textos_da_busca(client, modelo, topico: str, tipos: list[str]) -> dict[str, list[str]]:
    """Textos dos itens que a busca híbrida do tópico retorna (sem filtro de ano), por tipo.

    O perfil de todos os professores entra sempre: são poucos e todos podem virar candidatos.
    """
    emb = embedar_consulta(modelo, config.texto_topico(topico))
    textos = {}
    for tipo in tipos:
        if tipo == "professor":
            textos[tipo] = textos_da_colecao(client, COLECOES[tipo])
            continue
        pontos = busca_hibrida(client, COLECOES[tipo], emb, LIMITES[tipo])
        payloads = buscar_payloads(client, COLECOES[tipo], [p.payload["id"] for p in pontos])
        textos[tipo] = list(dict.fromkeys(str(p["texto"]) for p in payloads.values() if p.get("texto")))
    return textos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topicos", nargs="+", default=list(config.TOPICOS), help="padrão: todos do catálogo")
    parser.add_argument("--tipos", nargs="+", default=list(COLECOES), choices=list(COLECOES))
    parser.add_argument("--modo", choices=["texto", "nome", "partes"], default=None,
                        help=f"consulta do reranker (padrão: config.RERANK_CONSULTA = {config.RERANK_CONSULTA!r})")
    parser.add_argument("--todos", action="store_true", help="todos os itens, não só os resultados da busca")
    parser.add_argument("--lote", type=int, default=64, help="pares por gravação no disco")
    parser.add_argument("--estimar", action="store_true", help="só conta os pares que faltam, sem rodar o modelo")
    args = parser.parse_args()
    modo = args.modo or config.RERANK_CONSULTA

    disco = cache_disco()
    if disco is None:
        raise SystemExit("config.RERANK_CACHE_PATH está desligado (None)")

    # textos por (tópico, tipo)
    client = conectar_Qdrant()
    try:
        if args.todos:
            todos = {tipo: textos_da_colecao(client, COLECOES[tipo]) for tipo in args.tipos}
            textos = {t: todos for t in args.topicos}
        else:
            modelo = carregar_modelo()
            textos = {t: textos_da_busca(client, modelo, t, args.tipos) for t in args.topicos}
    finally:
        client.close()

    print(f"Modo de consulta: {modo} | itens: {'todos' if args.todos else 'resultados da busca'} | "
          f"cache: {disco.caminho} ({len(disco)} notas salvas)")

    pendentes: list[tuple[str, tuple[str, str]]] = []
    for t in args.topicos:
        consultas = reranking.consultas_rerank(t, config.texto_topico(t), modo)
        print(f"\n{t}: {len(consultas)} consulta(s)")
        for tipo in args.tipos:   # perfis primeiro: são os mais caros e sempre usados
            pares = [(q, txt) for q in consultas for txt in textos[t][tipo]]
            chaves = [chave(q, txt, reranking.RERANK_MAX_LENGTH) for q, txt in pares]
            salvos = disco.buscar(chaves)
            faltam = [p for p, k in zip(pares, chaves) if k not in salvos]
            print(f"  {tipo:<11} {len(textos[t][tipo]):>5} textos | {len(pares):>6} pares | faltam {len(faltam):>6}")
            pendentes += [(f"{t}/{tipo}", p) for p in faltam]

    pendentes = list({p: (rotulo, p) for rotulo, p in pendentes}.values())   # sem pares repetidos
    print(f"\nTotal a calcular: {len(pendentes)} pares")
    if args.estimar or not pendentes:
        return

    reranker = reranking.carregar_reranker()
    inicio = time.perf_counter()
    for i in range(0, len(pendentes), args.lote):
        lote = pendentes[i:i + args.lote]
        reranking.calcular_scores(reranker, [p for _, p in lote])   # calcula e grava no disco
        feitos = i + len(lote)
        decorrido = time.perf_counter() - inicio
        restante = decorrido / feitos * (len(pendentes) - feitos)
        print(f"  {feitos}/{len(pendentes)} ({lote[-1][0]}) | {decorrido / 60:.1f} min | falta ~{restante / 60:.1f} min",
              flush=True)
    print(f"Pronto. Cache com {len(disco)} notas.")


if __name__ == "__main__":
    main()
