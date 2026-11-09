from recuperacao.sistema_de_busca import config

ROTULOS = {
    "trabalho": ("Trabalhos relevantes (iniciação científica)", "Score do trabalho"),
    "projeto": ("Projetos relevantes", "Score do projeto"),
    "disciplina": ("Disciplinas relevantes", "Score da disciplina"),
    "producao": ("Produções relevantes", "Score da produção"),
    "orientacao": ("Orientações relevantes", "Score da orientação"),
}

ROTULO_SUBTIPO = {
    "livro": "Livro",
    "artigo_periodico": "Artigo em periódico",
    "capitulo_livro": "Capítulo de livro",
    "trabalho_congresso": "Trabalho em congresso",
    "resumo_expandido": "Resumo expandido",
    "pesquisa": "Projeto de pesquisa",
    "extensao": "Projeto de extensão",
    "desenvolvimento": "Projeto de desenvolvimento",
}


def _rotulo_subtipo(subtipo):
    if not subtipo:
        return None
    return ROTULO_SUBTIPO.get(subtipo, str(subtipo).replace("_", " ").capitalize())

def _fmt(valor):
    return f"{valor:.6f}" if valor is not None else "N/A"


def _melhores_itens(prof: dict, n: int, incluir_fracos: bool = True) -> dict[str, list[dict]]:
    """Os n itens de maior score de cada coleção, entre todos os tópicos; item repetido fica com o melhor score.

    incluir_fracos=False ignora os itens mantidos só como "melhor do tipo" (abaixo do corte).
    """
    melhores: dict[str, dict] = {}
    for topico, detalhe in prof["topicos"].items():
        for tipo, itens in detalhe["itens"].items():
            da_colecao = melhores.setdefault(tipo, {})
            for item in itens:
                if not incluir_fracos and item.get("corte") == "melhor_do_tipo":
                    continue
                if item["id"] not in da_colecao or item["score"] > da_colecao[item["id"]]["score"]:
                    da_colecao[item["id"]] = {**item, "topico": topico}
    return {
        tipo: sorted(itens.values(), key=lambda x: x["score"], reverse=True)[:n]
        for tipo, itens in melhores.items()
    }


def imprimir_ranking(ranking: list[dict], aluno_texto: str, n_itens: int = 3) -> None:
    print("CONSULTA DO ALUNO")
    print(aluno_texto)
    print("\n" + "=" * 100)
    print("RANKING COMPLETO")
    print("=" * 100)

    for i, prof in enumerate(ranking, start=1):
        print("=" * 100)
        print(f"{i}º - {prof['nome'] or prof['professor_id']}")
        print(f"Rerank score: {_fmt(prof['score'])}")
        print(f"Score inicial: {_fmt(prof.get('score_inicial'))}")
        print("Cobertura: " + " · ".join(f"{t} {_fmt(s)}" for t, s in prof["scores_topicos"].items()))

        mostrar_fracos = config.MOSTRAR_EVIDENCIA_FRACA
        todos = _melhores_itens(prof, 10**6)
        fortes = _melhores_itens(prof, 10**6, incluir_fracos=False)
        for tipo, itens in _melhores_itens(prof, n_itens, incluir_fracos=mostrar_fracos).items():
            titulo_secao, rotulo_score = ROTULOS.get(tipo, (tipo, "Score"))
            print(f"\n{titulo_secao}:")
            ocultos = 0 if mostrar_fracos else len(todos.get(tipo, [])) - len(fortes.get(tipo, []))
            if not itens:
                print("Nenhum item relevante encontrado.")
            if ocultos:
                print(f"  ({ocultos} item(ns) com evidência fraca oculto(s) — conta(m) no score)")
            for j, item in enumerate(itens, start=1):
                subtipo = _rotulo_subtipo(item.get("subtipo"))
                prefixo = f"[{subtipo}] " if subtipo else ""
                codigo = item.get("codigo")
                sigla = f"[{codigo}] " if codigo else ""
                print(f"\n  {j}. {prefixo}{sigla}{item['titulo'] or '(sem título)'}")
                aviso = " [abaixo do corte, mantido como melhor do tipo]" if item.get("corte") == "melhor_do_tipo" else ""
                print(f"     {rotulo_score}: {_fmt(item['score'])} (tópico: {item['topico']}){aviso}")


def imprimir_pre_ranking(ranking: list[dict], aluno_texto: str, n_itens: int = 3) -> None:
    """Ranking da 1ª/2ª etapa (só busca híbrida, sem reranking)."""
    print("CONSULTA DO ALUNO")
    print(aluno_texto)
    print("\n" + "=" * 100)
    print("PRÉ-RANKING (busca híbrida, antes do reranking)")
    print("=" * 100)

    for i, prof in enumerate(ranking, start=1):
        print("=" * 100)
        print(f"{i}º - {prof['nome'] or prof['professor_id']}")
        print(f"Score inicial: {_fmt(prof['score'])}")
        print("Cobertura: " + " · ".join(f"{t} {_fmt(s)}" for t, s in prof["scores_topicos"].items()))
        for topico, det in prof["topicos"].items():
            comps = " · ".join(f"{nome} {_fmt(v)}" for nome, v in det["componentes"].items())
            print(f"  [{topico}] score {_fmt(det['score'])} = {comps}")

        for tipo, itens in _melhores_itens(prof, n_itens).items():
            titulo_secao, _ = ROTULOS.get(tipo, (tipo, "Score"))
            print(f"\n{titulo_secao}:")
            if not itens:
                print("Nenhum item encontrado na busca.")
            for j, item in enumerate(itens, start=1):
                subtipo = _rotulo_subtipo(item.get("subtipo"))
                prefixo = f"[{subtipo}] " if subtipo else ""
                codigo = item.get("codigo")
                sigla = f"[{codigo}] " if codigo else ""
                print(f"\n  {j}. {prefixo}{sigla}{item['titulo'] or '(sem título)'}")
                print(f"     Score da busca: {_fmt(item['score'])} (tópico: {item['topico']})")


def imprimir_comparacao(pre: list[dict], final: list[dict]) -> None:
    """Posição de cada professor antes e depois do reranking."""
    pos_pre = {p["professor_id"]: i for i, p in enumerate(pre, start=1)}
    score_pre = {p["professor_id"]: p["score"] for p in pre}
    print("\n" + "=" * 100)
    print("COMPARAÇÃO: PRÉ-RANKING x RERANKING")
    print("=" * 100)
    print(f"{'Final':>5}  {'Pré':>5}  {'Δ':>4}  {'Score busca':>11}  {'Rerank':>9}  Professor")
    for i, prof in enumerate(final, start=1):
        pid = prof["professor_id"]
        antes = pos_pre.get(pid)
        delta = f"{antes - i:+d}" if antes else "novo"
        print(f"{i:>5}  {antes or '—':>5}  {delta:>4}  {_fmt(score_pre.get(pid)):>11}  "
              f"{_fmt(prof['score']):>9}  {prof['nome'] or pid}")
    if config.MIN_SCORE_PROFESSOR_RELATIVO and final:
        print(f"\nCorte de professores: rerank >= {config.MIN_SCORE_PROFESSOR_RELATIVO:.0%} do 1º "
              f"({config.MIN_SCORE_PROFESSOR_RELATIVO * final[0]['score']:.6f})")
    fora = [p for p in pre if p["professor_id"] not in {f["professor_id"] for f in final}]
    if fora:
        print("\nSaíram do top após o reranking: " + ", ".join(
            f"{p['nome'] or p['professor_id']} (pré {pos_pre[p['professor_id']]}º)" for p in fora))


_ETAPAS_TEMPO = [
    ("busca", "Busca (1ª/2ª etapas)", 0),
    ("embedding", "embedding da consulta", 1),
    ("qdrant", "consultas ao Qdrant", 1),
    ("reranking", "Reranking (3ª etapa)", 0),
    ("candidatos", "montagem dos candidatos (payloads)", 1),
    ("modelo_reranker", "modelo reranker", 1),
    ("total", "Total", 0),
]


def imprimir_tempos(tempos: dict[str, float], titulo: str = "TEMPOS") -> None:
    """tempos: rec.tempos logo após recomendar() ou pre_ranking()."""
    print("\n" + "=" * 100)
    print(titulo)
    print("=" * 100)
    total = tempos.get("total") or 0.0
    for chave, rotulo, nivel in _ETAPAS_TEMPO:
        if chave not in tempos:
            continue
        seg = tempos[chave]
        perc = f" ({seg / total:5.1%})" if total and chave != "total" else ""
        print(f"{'    ' * nivel}{rotulo:<{40 - 4 * nivel}} {seg:8.3f} s{perc}")


# ---------------------------------------------------------------------------
# Salvar a saída em arquivo
# ---------------------------------------------------------------------------
import re as _re
import sys as _sys
from contextlib import contextmanager as _contextmanager
from datetime import datetime as _datetime
from pathlib import Path as _Path

PASTA_OUTPUT = _Path(__file__).resolve().parents[2] / "output"   # recuperacao/output


class _Tee:
    """Escreve ao mesmo tempo no terminal e no arquivo."""

    def __init__(self, *destinos):
        self.destinos = destinos

    def write(self, texto):
        for d in self.destinos:
            d.write(texto)
        return len(texto)

    def flush(self):
        for d in self.destinos:
            d.flush()


@_contextmanager
def salvar_em_txt(nome: str = "ranking", pasta: _Path = PASTA_OUTPUT):
    """Tudo que for impresso dentro do `with` também vai para pasta/<data-hora>_<nome>.txt.

    Uso:
        with salvar_em_txt("grafos_matematica_discreta") as caminho:
            imprimir_ranking(...)
    """
    pasta.mkdir(parents=True, exist_ok=True)
    nome_limpo = _re.sub(r"[^\w-]+", "_", nome).strip("_") or "ranking"
    caminho = pasta / f"{_datetime.now():%Y%m%d_%H%M%S}_{nome_limpo}.txt"
    original = _sys.stdout
    with open(caminho, "w", encoding="utf-8") as arquivo:
        _sys.stdout = _Tee(original, arquivo)
        try:
            yield caminho
        finally:
            _sys.stdout = original
    print(f"\nSaída salva em: {caminho}")
