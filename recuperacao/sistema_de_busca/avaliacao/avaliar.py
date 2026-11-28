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
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --gerar-modelo             # cria consultas_manuais.json
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --conjunto manual          # suas consultas
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --n 5 --so-pre        # teste rápido, sem reranker
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --n 0 --modos hibrida densa
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --so-pre --modos hibrida --uniao media max top_m decaimento
        (compara as formas de unir os tópicos; cada configuração vira "<modo>/uniao=<valor>")

Análise de sensibilidade (--variar): muda UM parâmetro por vez, mantendo os demais como em config.py.
A configuração atual (sem sufixo) é a referência do Wilcoxon e das colunas "dif".
    python -m recuperacao.sistema_de_busca.avaliacao.avaliar --modos hibrida --n 150 \
        --variar corte=0,0.05,0.2 peso_texto=1.0,1.5 rerank_consulta=nome,texto pesos=iguais
    Parâmetros: {PARAMS}
    Os que só afetam o reranking (corte, corte_por_tipo, rerank_consulta, final_k) não geram
    linha de pré-ranking (seria igual à base) e são ignorados com --so-pre.

Saída: terminal + recuperacao/output/avaliacao_<data-hora>/ (log, consultas.csv, resumo.csv, resumo.json).
"""
import argparse
import csv
import json
import copy
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from statistics import mean

from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.avaliacao import conjunto, metricas
from recuperacao.sistema_de_busca.busca.agregacao import MODOS_UNIAO
from recuperacao.sistema_de_busca.busca.exibicao import PASTA_OUTPUT, salvar_em_txt

MODOS = ["densa", "esparsa", "hibrida"]
LARGURA = 36   # coluna "configuração" no resumo (cabe "hibrida+rerank/rerank_consulta=partes")


def _bool(v: str) -> bool:
    if v.lower() in ("sim", "true", "1"):
        return True
    if v.lower() in ("nao", "não", "false", "0"):
        return False
    raise ValueError(f"esperado sim/nao: {v!r}")


# nome no --variar -> (atributo em config, conversor, só afeta o reranking?)
PARAMETROS = {
    "corte":              ("MIN_RERANK_RELATIVO", float, True),
    "corte_por_tipo":     ("CORTE_POR_TIPO", _bool, True),
    "rerank_consulta":    ("RERANK_CONSULTA", str, True),
    "fragmentos":         ("TEXTO_LIVRE_FRAGMENTOS", str, True),
    "min_palavras":       ("TEXTO_LIVRE_MIN_PALAVRAS", int, True),
    "final_k":            ("FINAL_PROFESSOR_K", int, True),
    "peso_texto":         ("PESO_TEXTO_LIVRE", float, False),
    "bonus_disciplina":   ("BONUS_DISCIPLINA_TEMA", float, False),
    "peso_professor":     ("PESO_PROFESSOR", float, False),
    "decaimento":         ("DECAIMENTO", str, False),
    "uniao":              ("UNIAO_TOPICOS", str, False),
    "pesos":              (None, str, False),   # predefinição: "documento" (config.py) ou "iguais"
}
__doc__ = __doc__.replace("{PARAMS}", ", ".join(PARAMETROS))


def _pesos_iguais() -> None:
    """Todas as fontes (e o perfil) com o mesmo peso global e todos os subtipos com peso interno 1."""
    peso = 1.0 / (len(config.FONTES_ITENS) + 1)
    config.PESO_PROFESSOR = peso
    for cfg in config.FONTES_ITENS.values():
        cfg["peso_global"] = peso
        cfg["pesos_internos"] = {t: 1.0 for t in cfg.get("pesos_internos", {"padrao": 1.0})}


@contextmanager
def aplicar_variacao(variacao: tuple[str, object] | None):
    """Troca um parâmetro do config durante o bloco e restaura no fim (inclusive FONTES_ITENS)."""
    if variacao is None:
        yield
        return
    nome, valor = variacao
    atributo = PARAMETROS[nome][0]
    salvos = {a: copy.deepcopy(getattr(config, a)) for a in ("FONTES_ITENS", "PESO_PROFESSOR")}
    if atributo:
        salvos[atributo] = getattr(config, atributo)
    try:
        if nome == "pesos":
            if valor == "iguais":
                _pesos_iguais()
            elif valor != "documento":
                raise ValueError(f"pesos: use 'documento' ou 'iguais', não {valor!r}")
        else:
            setattr(config, atributo, valor)
        yield
    finally:
        for a, v in salvos.items():
            setattr(config, a, v)


def ler_variacoes(itens: list[str]) -> list[tuple[str, object]]:
    """["corte=0,0.2", "pesos=iguais"] -> [("corte", 0.0), ("corte", 0.2), ("pesos", "iguais")].
    Valores iguais ao atual do config são descartados (já são a base)."""
    variacoes = []
    for item in itens:
        nome, _, valores = item.partition("=")
        if nome not in PARAMETROS or not valores:
            raise SystemExit(f"--variar {item!r}: use nome=v1,v2 com nome em {', '.join(PARAMETROS)}")
        atributo, conv, _ = PARAMETROS[nome]
        atual = getattr(config, atributo) if atributo else "documento"
        for bruto in valores.split(","):
            try:
                valor = conv(bruto.strip())
            except ValueError as erro:
                raise SystemExit(f"--variar {nome}: {erro}")
            if nome == "pesos" and valor not in ("documento", "iguais"):
                raise SystemExit("--variar pesos: use 'documento' ou 'iguais'")
            if valor != atual and (nome, valor) not in variacoes:
                variacoes.append((nome, valor))
    return variacoes


def rodar_modo(rec, consultas: list[dict], modo: str, k: int, top_k: int, so_pre: bool,
               variacao: tuple[str, object] | None = None) -> list[dict]:
    """Roda todas as consultas com config.MODO_BUSCA = modo e a variação de parâmetro dada (None = base);
    uma linha por (consulta, configuração)."""
    so_rerank = variacao is not None and PARAMETROS[variacao[0]][2]
    if so_rerank and so_pre:
        print(f"  [{modo}] {variacao[0]} só afeta o reranking: ignorado com --so-pre")
        return []
    sufixo = f"/{variacao[0]}={variacao[1]}" if variacao else ""
    antigo, config.MODO_BUSCA = config.MODO_BUSCA, modo
    linhas, inicio = [], time.perf_counter()
    try:
        with aplicar_variacao(variacao):
            for i, q in enumerate(consultas, start=1):
                rec.excluir = q["excluir"]
                try:
                    resultados = {}
                    if not so_rerank:
                        resultados[f"{modo}{sufixo}"] = rec.pre_ranking(q["topicos"], top_k=top_k)
                    if not so_pre:
                        resultados[f"{modo}+rerank{sufixo}"] = rec.recomendar(q["topicos"], top_k=top_k)
                finally:
                    rec.excluir = {}
                for nome, profs in resultados.items():
                    ranking = [p["professor_id"] for p in profs]
                    linhas.append({
                        "conjunto": q["conjunto"], "configuracao": nome, "consulta_id": q["id"], "consulta": q["titulo"], "ano": q["ano"],
                        "esperados": " ".join(sorted(q["relevantes"])), "ranking": " ".join(ranking),
                        "ranking_nomes": " | ".join(f"{p['nome'] or p['professor_id']} ({p['score']:.4f})" for p in profs),
                        **metricas.todas(ranking, q["relevantes"], k),
                        "_profs": profs,
                    })
                if i % 10 == 0 or i == len(consultas):
                    print(f"  [{modo}{sufixo}] {i}/{len(consultas)} consultas ({time.perf_counter() - inicio:.0f} s)", flush=True)
    finally:
        config.MODO_BUSCA = antigo
    return linhas


def imprimir_rankings(linhas: list[dict], consultas: list[dict], nomes_prof: dict[str, str], k: int) -> None:
    """Ranking de cada consulta em cada configuração; ★ = esperado alta (ou o orientador), ☆ = esperado média."""
    por_consulta: dict[tuple[str, str], list[dict]] = {}
    for l in linhas:
        por_consulta.setdefault((l["conjunto"], l["consulta_id"]), []).append(l)
    print("\n" + "=" * 100)
    print("RANKINGS POR CONSULTA  (★ esperado alta/orientador · ☆ esperado média)")
    print("=" * 100)
    for q in consultas:
        rel = q["relevantes"]
        marca = lambda pid: "★" if rel.get(pid, 0) >= max(rel.values()) else ("☆" if pid in rel else " ")
        print(f"\n[{q['conjunto']}] {q['id']}: {q['titulo']}")
        if len(q["topicos"]) > 1 or next(iter(q["topicos"])) != conjunto.NOME_TEXTO_LIVRE:
            print(f"  temas/texto: {', '.join(q['topicos'])}")
        print("  esperados: " + ", ".join(f"{marca(pid)} {nomes_prof.get(pid, pid)}"
                                          for pid in sorted(rel, key=lambda x: -rel[x])))
        for l in por_consulta.get((q["conjunto"], q["id"]), []):
            print(f"  {l['configuracao']}  (nDCG@{k} {l[f'ndcg@{k}']:.3f} · MRR {l['mrr']:.3f})")
            for i, p in enumerate(l["_profs"], start=1):
                print(f"    {i:>2}. {marca(p['professor_id'])} {p['nome'] or p['professor_id']:<45} {p['score']:.4f}")


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
                r[f"delta_{m}"] = mean(a[m] - b[m] for a, b in pares) if pares else None
                r[f"p_{m}"] = _wilcoxon([a[m] for a, _ in pares], [b[m] for _, b in pares])
        resumo.append(r)
    ordem = {nome: i for i, nome in enumerate(c for m in MODOS for c in (m, f"{m}+rerank"))}
    variacoes = list(dict.fromkeys(l["configuracao"].partition("/")[2] for l in linhas))
    conjuntos = list(dict.fromkeys(l["conjunto"] for l in linhas))
    return sorted(resumo, key=lambda r: (conjuntos.index(r["conjunto"]),
                                         ordem.get(r["configuracao"].partition("/")[0], 99),
                                         variacoes.index(r["configuracao"].partition("/")[2])))


def imprimir_resumo(resumo: list[dict], k: int, referencia: str) -> None:
    nomes = metricas.nomes(k)
    print("\n" + "=" * 100)
    print(f"RESUMO (média por consulta) | p = Wilcoxon pareado contra {referencia}")
    print("=" * 100)
    cabecalho = (f"{'configuração':<{LARGURA}} {'n':>4}  " + "  ".join(f"{m:>9}" for m in nomes)
                 + f"  {'dif nDCG':>8}  {'p nDCG':>8}  {'dif MRR':>8}  {'p MRR':>8}")
    conjunto_atual = None
    for r in resumo:
        if r["conjunto"] != conjunto_atual:
            conjunto_atual = r["conjunto"]
            print(f"\n[{conjunto_atual}]\n{cabecalho}")
        extras = [(r.get(f"delta_ndcg@{k}"), "+8.3f"), (r.get(f"p_ndcg@{k}"), "8.4f"),
                  (r.get("delta_mrr"), "+8.3f"), (r.get("p_mrr"), "8.4f")]
        print(f"{r['configuracao']:<{LARGURA}} {r['consultas']:>4}  " + "  ".join(f"{r[m]:>9.3f}" for m in nomes)
              + "".join(f"  {v:>{fmt}}" if v is not None else f"  {'—':>8}" for v, fmt in extras))
    print("\ndif = média da diferença por consulta contra a referência (positivo = melhor).")
    print("\np < 0,05: diferença provavelmente real; acima disso pode ser ruído da amostra.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conjunto", nargs="+", choices=["tcc", "ic", "manual", "ambos"], default=["tcc"],
                        help="um ou mais; 'ambos' = tcc + ic")
    parser.add_argument("--arquivo", default=str(conjunto.ARQUIVO_MANUAL), help="JSON das consultas manuais")
    parser.add_argument("--gerar-modelo", action="store_true", help="cria o JSON de consultas manuais e sai")
    parser.add_argument("--n", type=int, default=150, help="quantos TCCs sortear (0 = todos os 373)")
    parser.add_argument("--n-ic", type=int, default=0, help="quantas ICs sortear (0 = todas as 139)")
    parser.add_argument("--consulta-ic", nargs="+", choices=list(conjunto.CONSULTAS_IC), default=list(conjunto.CONSULTAS_IC),
                        help="texto usado como consulta nas ICs (padrão: as duas versões)")
    parser.add_argument("--anos", type=int, nargs=2, metavar=("DE", "ATE"), help="só TCCs desses anos")
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--k", type=int, default=5, help="corte das métricas (nDCG@k, Recall@k)")
    parser.add_argument("--top-k", type=int, default=10, help="tamanho do ranking pedido ao sistema")
    parser.add_argument("--modos", nargs="+", choices=MODOS, default=MODOS)
    parser.add_argument("--rankings", choices=["auto", "sim", "nao"], default="auto",
                        help="imprime o ranking de cada consulta (auto: só para o conjunto manual)")
    parser.add_argument("--uniao", nargs="+", choices=list(MODOS_UNIAO),
                        help="formas de unir os tópicos a comparar (padrão: só config.UNIAO_TOPICOS, sem sufixo)")
    parser.add_argument("--variar", nargs="+", default=[], metavar="NOME=V1,V2",
                        help="análise de sensibilidade, um parâmetro por vez: " + ", ".join(PARAMETROS))
    parser.add_argument("--normalizar-topicos", choices=["sim", "nao"],
                        help="sobrescreve config.NORMALIZAR_TOPICOS nesta execução")
    parser.add_argument("--so-pre", action="store_true", help="só o pré-ranking (não carrega o reranker)")
    args = parser.parse_args()

    from recuperacao.sistema_de_busca.busca.service import Recomendador
    from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant
    from recuperacao.sistema_de_busca.modelo import carregar_modelo

    client = conectar_Qdrant()
    if args.gerar_modelo:
        conjunto.gerar_modelo_manual(client, Path(args.arquivo))
        return
    conjuntos = set(args.conjunto) | ({"tcc", "ic"} if "ambos" in args.conjunto else set())
    consultas = []
    if "manual" in conjuntos:
        consultas += conjunto.consultas_manuais(client, Path(args.arquivo))
    if "tcc" in conjuntos:
        consultas += conjunto.consultas_tcc(client, args.n or None, tuple(args.anos) if args.anos else None, args.semente)
    if "ic" in conjuntos:
        for versao in args.consulta_ic:
            consultas += conjunto.consultas_ic(client, versao, args.n_ic or None, args.semente)
    if not consultas:
        raise SystemExit("Nenhuma consulta encontrada com esses filtros.")

    reranker = None
    if not args.so_pre:
        from recuperacao.sistema_de_busca.busca.reranking import carregar_reranker
        reranker = carregar_reranker()
    rec = Recomendador(client, carregar_modelo(), reranker)
    if args.normalizar_topicos:
        config.NORMALIZAR_TOPICOS = args.normalizar_topicos == "sim"
    # --uniao é atalho para --variar uniao=...
    itens_variar = list(args.variar) + ([f"uniao={','.join(args.uniao)}"] if args.uniao else [])
    variacoes = [None] + ler_variacoes(itens_variar)
    modo_ref = "hibrida" if "hibrida" in args.modos else args.modos[-1]
    referencia = modo_ref if args.so_pre else f"{modo_ref}+rerank"

    pasta = PASTA_OUTPUT / f"avaliacao_{datetime.now():%Y%m%d_%H%M%S}"
    pasta.mkdir(parents=True, exist_ok=True)
    with salvar_em_txt("log", pasta):
        contagem = {}
        for q in consultas:
            contagem[q["conjunto"]] = contagem.get(q["conjunto"], 0) + 1
        print(f"Consultas: {contagem} | k={args.k} | top_k={args.top_k} | modos={args.modos} | "
              f"normalização={'sim' if config.NORMALIZAR_SCORES_BUSCA else 'não'} | "
              f"união={config.UNIAO_TOPICOS} (normalizar tópicos: {'sim' if config.NORMALIZAR_TOPICOS else 'não'}, "
              f"peso texto livre: {config.PESO_TEXTO_LIVRE}) | reranker={'não' if args.so_pre else 'sim'}")
        if len(variacoes) > 1:
            print("Variações (uma por vez, demais parâmetros como em config.py): "
                  + ", ".join(f"{n}={v}" for n, v in variacoes[1:]))
        linhas = []
        for modo in args.modos:
            for variacao in variacoes:
                linhas += rodar_modo(rec, consultas, modo, args.k, args.top_k, args.so_pre, variacao)
        resumo = resumir(linhas, args.k, referencia)
        mostrar = args.rankings == "sim" or (args.rankings == "auto" and conjuntos == {"manual"})
        if mostrar:
            nomes_prof = {str(p["id"]): p.get("nome")
                          for p in conjunto._scroll(client, config.COLLECTION_PROFESSORES, ["id", "nome"])}
            imprimir_rankings(linhas, consultas, nomes_prof, args.k)
        imprimir_resumo(resumo, args.k, referencia)
        for l in linhas:
            l.pop("_profs", None)

    for nome, dados in (("consultas.csv", linhas), ("resumo.csv", resumo)):
        campos = list(dict.fromkeys(c for d in dados for c in d))
        with open(pasta / nome, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(dados)
    (pasta / "resumo.json").write_text(json.dumps({"argumentos": vars(args), "referencia": referencia,
                                                   "variacoes": [f"{n}={v}" for n, v in variacoes[1:]], "resumo": resumo},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nArquivos em {pasta}")


if __name__ == "__main__":
    main()
