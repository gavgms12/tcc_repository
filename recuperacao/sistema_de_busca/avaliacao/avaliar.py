"""Compara busca densa, esparsa e híbrida, sem e com reranking, nos conjuntos trabalho -> orientador
(TCC pelo título; IC pelo título e pelo título + palavras-chave).

Para cada modo de busca (config.MODO_BUSCA) roda, nas MESMAS consultas:
    <modo>          pré-ranking (só a busca, sem reranker)
    <modo>+rerank   ranking final (com reranker)
e mede nDCG@k, MRR, Recall@k e Hit@1 no ranking de professores. Dentro de cada conjunto, cada configuração é
comparada com a referência (híbrida+rerank) por teste de Wilcoxon pareado.

Exemplos (da raiz do repositório):
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --n 150                    # TCC
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --conjunto ambos --n 150   # TCC + IC (título e título+palavras)
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --n 5 --so-pre        # teste rápido, sem reranker
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --n 0 --modos hibrida densa

Saída: terminal + recuperacao/output/avaliacao_<data-hora>/ (log, consultas.csv, resumo.csv, resumo.json).
"""
import argparse
import csv
import json
import time
from datetime import datetime
from statistics import mean

from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.avaliacao import conjunto, metricas
from recuperacao.sistema_de_busca.busca.exibicao import PASTA_OUTPUT, salvar_em_txt

MODOS = ["densa", "esparsa", "hibrida"]


def rodar_modo(rec, consultas: list[dict], modo: str, k: int, top_k: int, so_pre: bool) -> list[dict]:
    """Roda todas as consultas com config.MODO_BUSCA = modo; uma linha por (consulta, configuração)."""
    antigo, config.MODO_BUSCA = config.MODO_BUSCA, modo
    linhas, inicio = [], time.perf_counter()
    try:
        for i, q in enumerate(consultas, start=1):
            rec.excluir = q["excluir"]
            try:
                rankings = {modo: [p["professor_id"] for p in rec.pre_ranking(q["topicos"], top_k=top_k)]}
                if not so_pre:
                    rankings[f"{modo}+rerank"] = [p["professor_id"] for p in rec.recomendar(q["topicos"], top_k=top_k)]
            finally:
                rec.excluir = {}
            for nome, ranking in rankings.items():
                linhas.append({
                    "conjunto": q["conjunto"], "configuracao": nome, "consulta_id": q["id"], "consulta": q["titulo"], "ano": q["ano"],
                    "esperados": " ".join(sorted(q["relevantes"])), "ranking": " ".join(ranking),
                    **metricas.todas(ranking, q["relevantes"], k),
                })
            if i % 10 == 0 or i == len(consultas):
                print(f"  [{modo}] {i}/{len(consultas)} consultas ({time.perf_counter() - inicio:.0f} s)", flush=True)
    finally:
        config.MODO_BUSCA = antigo
    return linhas


def _wilcoxon(a: list[float], b: list[float]) -> float | None:
    """p-valor do teste de Wilcoxon pareado (None se não houver diferença ou se o scipy faltar)."""
    try:
        from scipy.stats import wilcoxon
    except ImportError:
        return None
    if all(x == y for x, y in zip(a, b)):
        return None
    return float(wilcoxon(a, b).pvalue)


def resumir(linhas: list[dict], k: int, referencia: str) -> list[dict]:
    grupos: dict[tuple[str, str], list[dict]] = {}
    for l in linhas:
        grupos.setdefault((l["conjunto"], l["configuracao"]), []).append(l)
    resumo = []
    for (conj, nome), grupo in grupos.items():
        ref = {l["consulta_id"]: l for l in grupos.get((conj, referencia), [])}
        r = {"conjunto": conj, "configuracao": nome, "consultas": len(grupo),
             **{m: mean(l[m] for l in grupo) for m in metricas.nomes(k)}}
        if ref and nome != referencia:
            pares = [(l, ref[l["consulta_id"]]) for l in grupo if l["consulta_id"] in ref]
            for m in (f"ndcg@{k}", "mrr"):
                r[f"p_{m}"] = _wilcoxon([a[m] for a, _ in pares], [b[m] for _, b in pares])
        resumo.append(r)
    ordem = {nome: i for i, nome in enumerate(c for m in MODOS for c in (m, f"{m}+rerank"))}
    conjuntos = list(dict.fromkeys(l["conjunto"] for l in linhas))
    return sorted(resumo, key=lambda r: (conjuntos.index(r["conjunto"]), ordem.get(r["configuracao"], 99)))


def imprimir_resumo(resumo: list[dict], k: int, referencia: str) -> None:
    nomes = metricas.nomes(k)
    print("\n" + "=" * 100)
    print(f"RESUMO (média por consulta) | p = Wilcoxon pareado contra {referencia}")
    print("=" * 100)
    cabecalho = f"{'configuração':<16} {'n':>4}  " + "  ".join(f"{m:>9}" for m in nomes) + f"  {'p nDCG':>8}  {'p MRR':>8}"
    conjunto_atual = None
    for r in resumo:
        if r["conjunto"] != conjunto_atual:
            conjunto_atual = r["conjunto"]
            print(f"\n[{conjunto_atual}]\n{cabecalho}")
        p = [r.get(f"p_ndcg@{k}"), r.get("p_mrr")]
        print(f"{r['configuracao']:<16} {r['consultas']:>4}  " + "  ".join(f"{r[m]:>9.3f}" for m in nomes)
              + "".join(f"  {v:>8.4f}" if v is not None else f"  {'—':>8}" for v in p))
    print("\np < 0,05: diferença provavelmente real; acima disso pode ser ruído da amostra.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conjunto", choices=["tcc", "ic", "ambos"], default="tcc")
    parser.add_argument("--n", type=int, default=150, help="quantos TCCs sortear (0 = todos os 373)")
    parser.add_argument("--n-ic", type=int, default=0, help="quantas ICs sortear (0 = todas as 139)")
    parser.add_argument("--consulta-ic", nargs="+", choices=list(conjunto.CONSULTAS_IC), default=list(conjunto.CONSULTAS_IC),
                        help="texto usado como consulta nas ICs (padrão: as duas versões)")
    parser.add_argument("--anos", type=int, nargs=2, metavar=("DE", "ATE"), help="só TCCs desses anos")
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--k", type=int, default=5, help="corte das métricas (nDCG@k, Recall@k)")
    parser.add_argument("--top-k", type=int, default=10, help="tamanho do ranking pedido ao sistema")
    parser.add_argument("--modos", nargs="+", choices=MODOS, default=MODOS)
    parser.add_argument("--so-pre", action="store_true", help="só o pré-ranking (não carrega o reranker)")
    args = parser.parse_args()

    from recuperacao.sistema_de_busca.busca.service import Recomendador
    from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant
    from recuperacao.sistema_de_busca.modelo import carregar_modelo

    client = conectar_Qdrant()
    consultas = []
    if args.conjunto in ("tcc", "ambos"):
        consultas += conjunto.consultas_tcc(client, args.n or None, tuple(args.anos) if args.anos else None, args.semente)
    if args.conjunto in ("ic", "ambos"):
        for versao in args.consulta_ic:
            consultas += conjunto.consultas_ic(client, versao, args.n_ic or None, args.semente)
    if not consultas:
        raise SystemExit("Nenhuma consulta encontrada com esses filtros.")

    reranker = None
    if not args.so_pre:
        from recuperacao.sistema_de_busca.busca.reranking import carregar_reranker
        reranker = carregar_reranker()
    rec = Recomendador(client, carregar_modelo(), reranker)
    referencia = "hibrida" if args.so_pre else "hibrida+rerank"

    pasta = PASTA_OUTPUT / f"avaliacao_{datetime.now():%Y%m%d_%H%M%S}"
    pasta.mkdir(parents=True, exist_ok=True)
    with salvar_em_txt("log", pasta):
        contagem = {}
        for q in consultas:
            contagem[q["conjunto"]] = contagem.get(q["conjunto"], 0) + 1
        print(f"Consultas: {contagem} | k={args.k} | top_k={args.top_k} | modos={args.modos} | "
              f"normalização={'sim' if config.NORMALIZAR_SCORES_BUSCA else 'não'} | reranker={'não' if args.so_pre else 'sim'}")
        linhas = []
        for modo in args.modos:
            linhas += rodar_modo(rec, consultas, modo, args.k, args.top_k, args.so_pre)
        resumo = resumir(linhas, args.k, referencia)
        imprimir_resumo(resumo, args.k, referencia)

    for nome, dados in (("consultas.csv", linhas), ("resumo.csv", resumo)):
        campos = list(dict.fromkeys(c for d in dados for c in d))
        with open(pasta / nome, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(dados)
    (pasta / "resumo.json").write_text(json.dumps({"argumentos": vars(args), "referencia": referencia, "resumo": resumo},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nArquivos em {pasta}")


if __name__ == "__main__":
    main()
