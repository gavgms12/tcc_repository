#!/usr/bin/env python3
"""Gera arquivo .list para o scriptLattes a partir do JSON do scraping."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_INPUT = ROOT_DIR / "data" / "bronze" / "merged" / "professores.json"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "bronze" / "lista" / "professores.list"

LATTES_NUMERICO = re.compile(r"lattes\.cnpq\.br/(\d+)", re.IGNORECASE)


def extrair_id_lattes(url: str) -> str | None:
    match = LATTES_NUMERICO.search(url)
    if match:
        return match.group(1)

    parsed = urlparse(url)
    if "buscatextual" in parsed.netloc.lower():
        params = parse_qs(parsed.query)
        if params.get("id"):
            return params["id"][0].strip()

    return None


def gerar_linhas(professores: list[dict[str, str | None]]) -> list[str]:
    linhas: list[str] = []

    for professor in professores:
        id_lattes = professor.get("idLattes")
        if not id_lattes:
            endereco_lattes = professor.get("enderecoLattes")
            if endereco_lattes:
                id_lattes = extrair_id_lattes(endereco_lattes)

        if not id_lattes:
            continue

        nome = str(professor.get("nome", "")).strip()
        linhas.append(f"{id_lattes} , {nome}")

    return linhas


def salvar_lista(linhas: list[str], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas))
        arquivo.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Converte o JSON do scraping em arquivo .list para o scriptLattes."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Arquivo JSON gerado pelo scraping.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Arquivo .list de saída.",
    )
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as arquivo:
        professores = json.load(arquivo)

    linhas = gerar_linhas(professores)

    if not linhas:
        raise RuntimeError("Nenhum professor com ID Lattes encontrado no JSON.")

    salvar_lista(linhas, args.output)

    total = len(professores)
    ignorados = total - len(linhas)
    print(f"Geradas {len(linhas)} linhas no arquivo .list.")
    print(f"Ignorados {ignorados} professores sem enderecoLattes.")
    print(f"Arquivo salvo em: {args.output}")


if __name__ == "__main__":
    main()
