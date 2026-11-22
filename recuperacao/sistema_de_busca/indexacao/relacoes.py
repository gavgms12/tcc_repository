# indexacao/relacoes.py
import pandas as pd

# campo no JSON do professor -> tipo na tabela
CAMPOS_RELACAO = {
    "producoes": "producao",
    "projetos": "projeto",
    "orientacoes": "orientacao",
    "disciplinas": "disciplina",
    "trabalhosIniciacaoCientifica": "ic",
}


def construir_relacoes(professores: list[dict]) -> pd.DataFrame:
    linhas = []
    for professor in professores:
        professor_id = str(professor["siape"])
        for campo, tipo in CAMPOS_RELACAO.items():
            for objeto_id in professor.get(campo) or []:   # `or []` cobre None e lista vazia
                linhas.append({
                    "professor_id": professor_id,
                    "tipo": tipo,
                    "objeto_id": str(objeto_id),
                })

    return pd.DataFrame(
        linhas, columns=["professor_id", "tipo", "objeto_id"]
    ).drop_duplicates()
    
def anos_disciplinas(professores: list[dict]) -> dict[str, dict[str, list[int]]]:
    """idSigaa -> {siape: anos em que o professor lecionou a disciplina}, do perfil `disciplinasPorAno`.

    O ano é do par (professor, disciplina): a mesma disciplina pode ser recente para um e antiga para outro.
    """
    anos: dict[str, dict[str, set[int]]] = {}
    for professor in professores:
        professor_id = str(professor["siape"])
        for ano, ids in (professor.get("disciplinasPorAno") or {}).items():
            for objeto_id in ids or []:
                anos.setdefault(str(objeto_id), {}).setdefault(professor_id, set()).add(int(ano))
    return {
        objeto_id: {pid: sorted(a, reverse=True) for pid, a in por_prof.items()}
        for objeto_id, por_prof in anos.items()
    }


def professores_por_objeto(relacoes, tipo):
    sub = relacoes[relacoes["tipo"] == tipo]
    return sub.groupby("objeto_id")["professor_id"].apply(list).to_dict()
