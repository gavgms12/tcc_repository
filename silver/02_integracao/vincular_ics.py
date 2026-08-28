#!/usr/bin/env python3
"""Vincula professores às disciplinas e enriquece o cadastro mesclado."""

import argparse
import requests
from bs4 import BeautifulSoup
import re
import sys
from datetime import datetime, timezone
import json
import unicodedata
from pathlib import Path
import urllib3

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_DOCENTES = ROOT_DIR / "data" / "bronze" / "raw" / "sigaa" / "docentes_sigaa.json"
DEFAULT_COMPONENTES = ROOT_DIR / "data" / "bronze" / "raw" / "sigaa" / "componentes_sigaa.json"
DEFAULT_TRABALHOS_VINCULADOS = ROOT_DIR / "data" / "bronze" / "raw" / "periodicos" / "trabalhos_vinculados.json"
DEFAULT_TRABALHOS = ROOT_DIR / "data" / "bronze" / "raw" / "periodicos" / "trabalhos_ic_periodicos.json"
DEFAULT_MERGED = ROOT_DIR / "data" / "bronze" / "merged" / "professores_sigaa_iesti_merged.json"

def normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()

def normalizar_nome(nome: str) -> str:
    nome = normalizar_texto(nome)
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(char for char in nome if not unicodedata.combining(char))
    return nome.upper()

def carregar_json(caminho: Path) -> dict | list:
    with caminho.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)

def salvar_json(dados: dict | list, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
        
def construir_padrao_professor(nome_normalizado: str) -> re.Pattern | None:
    tokens = nome_normalizado.split()

    primeiro_nome = tokens[0]
    sobrenomes = tokens[-2:] if len(tokens) >= 3 else tokens[-1:]

    meio = r"(?:\s+\S+){0,3}?"
    partes_sobrenome = r"\s+".join(re.escape(s) for s in sobrenomes)

    padrao = rf"\b{re.escape(primeiro_nome)}\b{meio}\s+{partes_sobrenome}\b"
    return re.compile(padrao)

def indice_professores_por_padrao(docentes_payload: dict) -> list[tuple[re.Pattern, dict]]:
    indice = []
    for docente in docentes_payload.get("docentes", []):
        nome_normalizado = normalizar_nome(docente.get("nome", ""))
        padrao = construir_padrao_professor(nome_normalizado)
        if padrao:
            indice.append((padrao, docente))
    return indice

def professores_citados(autores_texto: str, indice_padroes: list[tuple[re.Pattern, dict]]) -> list[dict]:
    autores_normalizado = normalizar_nome(autores_texto)
    encontrados = []

    for padrao, docente in indice_padroes:
        if padrao.search(autores_normalizado):
            encontrados.append(docente)

    return encontrados

def vincular_trabalhos_professores(trabalhos: list[dict],docentes_payload: dict,) -> list[dict]:
    indice_nomes = indice_professores_por_padrao(docentes_payload)

    for trabalho in trabalhos:
        autores_texto = trabalho.get("autores", "")
        professores = professores_citados(autores_texto, indice_nomes)

        trabalho["professoresVinculados"] = [
            {"siape": p.get("siape"), "nome": p.get("nome")}
            for p in professores
        ]

    return trabalhos

def enriquecer_merged_com_trabalhos(
    merged: list[dict],
    trabalhos_vinculados: list[dict],
) -> list[dict]:
    trabalhos_por_siape: dict[str, list[dict]] = {}

    for trabalho in trabalhos_vinculados:
        for professor_vinculado in trabalho.get("professoresVinculados", []):
            siape = professor_vinculado.get("siape")
            if not siape:
                continue
            trabalhos_por_siape.setdefault(siape, []).append(
                {
                    "titulo": trabalho.get("titulo"),
                    "autores": trabalho.get("autores"),
                    "resumo" : trabalho.get("resumo"),
                    "palavrasChaves": trabalho.get("palavrasChaves", []),
                    "ano" : trabalho.get("ano"),
                }
            )

    for professor in merged:
        siape = professor.get("siape")
        if not siape:
            continue

        professor["trabalhosIniciacaoCientifica"] = trabalhos_por_siape.get(siape, [])

    return merged

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vincula trabalhos de IC aos professores."
    )
    parser.add_argument("--docentes", type=Path, default=DEFAULT_DOCENTES)
    parser.add_argument("--trabalhos", type=Path, default=DEFAULT_TRABALHOS)
    parser.add_argument("--merged", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--sem-merged", action="store_true")
    parser.add_argument("--trabalhos-vinculados-output", type=Path, default=DEFAULT_TRABALHOS_VINCULADOS)
    parser.add_argument(
        "--buscar-ics-vinculadas",
        action="store_true",
        help="Busca ICs orientadas pelos docentes.",
    )
    args = parser.parse_args()

    if not args.docentes.exists():
        raise FileNotFoundError(f"Arquivo de docentes não encontrado: {args.docentes}")
    if not args.trabalhos.exists():
        raise FileNotFoundError(f"Arquivo de trabalhos não encontrado: {args.trabalhos}")
    
   
    docentes_payload = carregar_json(args.docentes)
    trabalhos = carregar_json(args.trabalhos)

    trabalhos_vinculados = vincular_trabalhos_professores(trabalhos, docentes_payload)
    salvar_json(trabalhos_vinculados, args.trabalhos_vinculados_output)

    if not args.sem_merged and args.merged.exists():
        merged = carregar_json(args.merged)
        enriquecer_merged_com_trabalhos(merged, trabalhos_vinculados)
        salvar_json(merged, args.merged)
        print(f"Professores + trabalhos de iniciação científica em: {args.merged}")

    com_professor = sum(1 for t in trabalhos_vinculados if t["professoresVinculados"])
    print(f"Trabalhos processados: {len(trabalhos_vinculados)} ({com_professor} vinculados a algum professor).")

if __name__ == "__main__":
    main()
