"""Compara o ranking final com RERANK_CONSULTA = "nome" e = "partes" para os mesmos tópicos.

Antes, pré-calcule as notas (senão o reranker roda na hora e demora):
    python -m recuperacao.sistema_de_busca.indexacao.prerankear --topicos Grafos "Matemática Discreta" --modo nome
    python -m recuperacao.sistema_de_busca.indexacao.prerankear --topicos Grafos "Matemática Discreta" --modo partes
Depois:
    python -m recuperacao.sistema_de_busca.comparar_modos
A saída também vai para recuperacao/output/<data-hora>_comparacao_modos_....txt
"""
from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.busca import reranking
from recuperacao.sistema_de_busca.busca.exibicao import _melhores_itens, salvar_em_txt
from recuperacao.sistema_de_busca.busca.service import Recomendador
from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant
from recuperacao.sistema_de_busca.modelo import carregar_modelo

SELECIONADOS = ["Matemática Discreta", "Grafos"]
MODOS = ["nome", "partes"]
TOP_K = 8
N_ITENS = 3


def main() -> None:
    topicos = {t: config.texto_topico(t) for t in SELECIONADOS}
    rec = Recomendador(conectar_Qdrant(), carregar_modelo(), reranking.carregar_reranker())
    original = config.RERANK_CONSULTA
    resultados, cortados = {}, {}
    try:
        with salvar_em_txt("comparacao_modos_" + "_".join(SELECIONADOS)):
            for modo in MODOS:
                config.RERANK_CONSULTA = modo
                antes = dict(reranking.estatisticas)
                resultados[modo] = rec.recomendar(topicos, top_k=TOP_K)
                cortados[modo] = rec.professores_cortados
                calc = reranking.estatisticas["pares_calculados"] - antes["pares_calculados"]
                disco = reranking.estatisticas["pares_do_disco"] - antes["pares_do_disco"]
                print(f"[{modo}] reranker {rec.tempos.get('modelo_reranker', 0):.1f}s | "
                      f"pares do disco: {disco} | calculados na hora: {calc}")

            # tabela lado a lado
            print("\n" + "=" * 100)
            print(f"RANKING FINAL: {' x '.join(MODOS)}   (tópicos: {', '.join(SELECIONADOS)})")
            print("=" * 100)
            pos = {m: {p["professor_id"]: (i, p) for i, p in enumerate(r, 1)} for m, r in resultados.items()}
            ids = list(dict.fromkeys(p["professor_id"] for m in MODOS for p in resultados[m]))
            ids.sort(key=lambda pid: min(pos[m].get(pid, (99, None))[0] for m in MODOS))
            print("".join(f"{m:>18}" for m in MODOS) + "   professor")
            for pid in ids:
                colunas, nome = "", None
                for m in MODOS:
                    i, p = pos[m].get(pid, (None, None))
                    colunas += f"{(f'{i}º  {p['score']:.4f}' if p else '—'):>18}"
                    nome = nome or (p and p["nome"])
                print(f"{colunas}   {nome or pid}")
            for m in MODOS:
                if cortados[m]:
                    print(f"[{m}] cortados: " + ", ".join(f"{n} ({s:.4f})" for n, s in cortados[m]))

            # evidência de cada professor em cada modo
            for pid in ids:
                nome = next(pos[m][pid][1]["nome"] for m in MODOS if pid in pos[m])
                print("\n" + "-" * 100)
                print(nome)
                for m in MODOS:
                    if pid not in pos[m]:
                        print(f"  [{m}] fora do ranking")
                        continue
                    print(f"  [{m}]")
                    for tipo, itens in _melhores_itens(pos[m][pid][1], N_ITENS, incluir_fracos=False).items():
                        for it in itens:
                            print(f"     {tipo:<10} {it['score']:.4f}  {str(it['titulo'])[:60]:<60}"
                                  f"  <- \"{str(it.get('consulta'))[:45]}\"")
    finally:
        config.RERANK_CONSULTA = original
        rec.client.close()


if __name__ == "__main__":
    main()
