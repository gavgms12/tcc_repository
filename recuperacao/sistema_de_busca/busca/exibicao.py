ROTULOS = {
    "trabalho": ("Trabalhos relevantes (iniciação científica)", "Score do trabalho"),
    "projeto": ("Projetos relevantes", "Score do projeto"),
    "disciplina": ("Disciplinas relevantes", "Score da disciplina"),
}


def _fmt(valor):
    return f"{valor:.6f}" if valor is not None else "N/A"


def imprimir_ranking(ranking: list[dict], aluno_texto: str) -> None:
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
        print(f"Score do perfil: {_fmt(prof.get('score_perfil'))}")

        for tipo, itens in prof["itens"].items():
            titulo_secao, rotulo_score = ROTULOS.get(tipo, (tipo, "Score"))
            print(f"\n{titulo_secao}:")
            if not itens:
                print("Nenhum item relevante encontrado.")
            for j, item in enumerate(itens, start=1):
                print(f"\n  {j}. {item['titulo'] or '(sem título)'}")
                print(f"     {rotulo_score}: {_fmt(item['score'])}")