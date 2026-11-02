#!/usr/bin/env python3
"""Unifica os perfis SIGAA + Lattes já limpos (Silver) num perfil por professor.

Esta é a única etapa da camada Gold: lê exclusivamente Parquets já limpos da
Silver (identidade, perfil SIGAA, perfil Lattes e catálogo de trabalhos de
IC/periódicos), vincula os trabalhos de IC ao professor orientador por
similaridade de nome, e grava o perfil unificado por professor — pronto para
embeddings (bge-m3) — na Gold. A Gold não lê nada da Bronze nem faz limpeza:
isso já aconteceu na Silver.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

sys.path.insert(0, str(ROOT_DIR / "silver" / "01_merge"))

from bronze.minio_storage import ler_parquet_silver, salvar_parquet_gold  # noqa: E402
from merge_professores import chave_nome, similaridade_nomes  # noqa: E402

DEFAULT_IDENTIDADE = "identidade_professores.parquet"
DEFAULT_PERFIL_SIGAA = "perfil_sigaa_limpo.parquet"
DEFAULT_PERFIL_LATTES = "perfil_lattes_limpo.parquet"
DEFAULT_TRABALHOS_IC = "trabalhos_ic_periodicos.parquet"
DEFAULT_SAIDA = "professores_unificados.parquet"

LIMIAR_SIMILARIDADE_ORIENTADOR = 0.92

PERFIL_SIGAA_VAZIO: dict[str, Any] = {
    "descricaoPessoal": None,
    "formacaoAcademicaProfissional": None,
    "areasInteresse": [],
    "disciplinasSigaa": [],
    "projetosSigaa": [],
    "producaoDocente": [],
}

PERFIL_LATTES_VAZIO: dict[str, Any] = {
    "resumo": None,
    "competencias": {"areas": [], "linhas_pesquisa": [], "palavras_chave": []},
    "producoes": [],
    "projetos": [],
    "orientacoes": [],
}


def extrair_orientador(autores_texto: str) -> str:
    """Por convenção, o último autor listado é o orientador do trabalho."""
    partes = [p.strip() for p in (autores_texto or "").split(",") if p.strip()]
    return partes[-1] if partes else ""


def vincular_trabalhos_ic(
    catalogo_trabalhos: list[dict],
    roster: list[dict],
) -> dict[str, list[str]]:
    """Casa cada trabalho de IC (já limpo na Silver) com um professor do
    roster pelo orientador. Retorna um mapa siape -> lista de ids de trabalhos."""
    roster_com_nome = [p for p in roster if p.get("nome")]

    trabalhos_por_siape: dict[str, list[str]] = {}
    for trabalho in catalogo_trabalhos:
        orientador = extrair_orientador(trabalho.get("autores", ""))
        if not orientador:
            continue

        melhor_professor = None
        melhor_score = 0.0
        for professor in roster_com_nome:
            score = similaridade_nomes(orientador, professor["nome"])
            if score >= LIMIAR_SIMILARIDADE_ORIENTADOR and score > melhor_score:
                melhor_score = score
                melhor_professor = professor

        if melhor_professor is None:
            continue

        siape = melhor_professor.get("siape")
        if siape:
            trabalhos_por_siape.setdefault(siape, []).append(trabalho["id"])

    return trabalhos_por_siape


def montar_professor(
    identidade: dict,
    perfis_sigaa_por_siape: dict[str, dict],
    perfis_lattes_por_id: dict[str, dict],
    trabalhos_por_siape: dict[str, list[str]],
) -> dict:
    nome = identidade.get("nome")
    id_lattes = identidade.get("idLattes")
    siape = identidade.get("siape")

    perfil_sigaa = perfis_sigaa_por_siape.get(siape, PERFIL_SIGAA_VAZIO) if siape else PERFIL_SIGAA_VAZIO
    perfil_lattes = perfis_lattes_por_id.get(id_lattes, PERFIL_LATTES_VAZIO) if id_lattes else PERFIL_LATTES_VAZIO

    if id_lattes and id_lattes not in perfis_lattes_por_id:
        print(f"AVISO: sem perfil Lattes limpo para {nome} (idLattes={id_lattes}).")

    resumo = perfil_lattes["resumo"] or perfil_sigaa["descricaoPessoal"]
    projetos = [*perfil_lattes["projetos"], *perfil_sigaa["projetosSigaa"]]

    return {
        "nome": nome,
        "idLattes": id_lattes,
        "siape": siape,
        "resumo": resumo,
        "formacaoAcademicaProfissional": perfil_sigaa["formacaoAcademicaProfissional"],
        "areasInteresse": perfil_sigaa["areasInteresse"],
        "competencias": perfil_lattes["competencias"],
        "producoes": perfil_lattes["producoes"],
        "producaoDocenteSigaa": perfil_sigaa["producaoDocente"],
        "projetos": projetos,
        "orientacoes": perfil_lattes["orientacoes"],
        "disciplinasSigaa": perfil_sigaa["disciplinasSigaa"],
        "trabalhosIniciacaoCientifica": trabalhos_por_siape.get(siape, []) if siape else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unifica os perfis SIGAA + Lattes já limpos na Silver e grava na Gold."
    )
    parser.add_argument("--identidade", default=DEFAULT_IDENTIDADE)
    parser.add_argument("--perfil-sigaa", default=DEFAULT_PERFIL_SIGAA)
    parser.add_argument("--perfil-lattes", default=DEFAULT_PERFIL_LATTES)
    parser.add_argument("--trabalhos-ic", default=DEFAULT_TRABALHOS_IC)
    parser.add_argument("--saida", default=DEFAULT_SAIDA)
    args = parser.parse_args()

    roster = ler_parquet_silver(args.identidade)
    perfis_sigaa_por_siape = {p["siape"]: p for p in ler_parquet_silver(args.perfil_sigaa) if p.get("siape")}
    perfis_lattes_por_id = {p["idLattes"]: p for p in ler_parquet_silver(args.perfil_lattes) if p.get("idLattes")}

    try:
        catalogo_trabalhos = ler_parquet_silver(args.trabalhos_ic)
    except Exception:
        catalogo_trabalhos = []

    trabalhos_por_siape = vincular_trabalhos_ic(catalogo_trabalhos, roster) if catalogo_trabalhos else {}

    professores = [
        montar_professor(identidade, perfis_sigaa_por_siape, perfis_lattes_por_id, trabalhos_por_siape)
        for identidade in roster
    ]
    salvar_parquet_gold(args.saida, professores)

    com_resumo = sum(1 for p in professores if p["resumo"])
    com_ic = sum(1 for p in professores if p["trabalhosIniciacaoCientifica"])
    print(f"Perfis unificados: {len(professores)} ({com_resumo} com resumo).")
    print(f"Professores com IC vinculada: {com_ic}.")
    print(f"Parquet salvo em: gold/{args.saida}")


if __name__ == "__main__":
    main()
