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


def _melhores_itens(prof: dict, n: int) -> dict[str, list[dict]]:
    """Os n itens de maior score de cada coleção, entre todos os tópicos; item repetido fica com o melhor score."""
    melhores: dict[str, dict] = {}
    for topico, detalhe in prof["topicos"].items():
        for tipo, itens in detalhe["itens"].items():
            da_colecao = melhores.setdefault(tipo, {})
            for item in itens:
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

        for tipo, itens in _melhores_itens(prof, n_itens).items():
            titulo_secao, rotulo_score = ROTULOS.get(tipo, (tipo, "Score"))
            print(f"\n{titulo_secao}:")
            if not itens:
                print("Nenhum item relevante encontrado.")
            for j, item in enumerate(itens, start=1):
                subtipo = _rotulo_subtipo(item.get("subtipo"))
                prefixo = f"[{subtipo}] " if subtipo else ""
                print(f"\n  {j}. {prefixo}{item['titulo'] or '(sem título)'}")
                print(f"     {rotulo_score}: {_fmt(item['score'])} (tópico: {item['topico']})")
