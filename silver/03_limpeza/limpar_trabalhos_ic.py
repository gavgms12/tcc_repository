#!/usr/bin/env python3
"""Limpa e normaliza o catálogo de trabalhos de IC/periódicos na camada Silver.

Só normaliza texto/ano e gera um ID estável por trabalho. O vínculo de cada
trabalho com o professor orientador (por similaridade de nome) é feito na
Gold, junto com o resto da unificação — aqui é só limpeza da fonte.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bronze.minio_storage import ler_json_bronze, salvar_parquet_silver  # noqa: E402

DEFAULT_TRABALHOS_IC = "raw/periodicos/trabalhos_ic_periodicos.json"
DEFAULT_SAIDA = "trabalhos_ic_periodicos.parquet"


def normalizar_texto(texto: str | None) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip()


def normalizar_ano(valor: str | int | None) -> int | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return int(texto) if texto.isdigit() else None


def gerar_id(tipo: str, titulo: str, ano: int | None) -> str:
    base = f"{tipo}|{titulo}|{ano or ''}".lower()
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def limpar_trabalhos(trabalhos_brutos: list[dict]) -> list[dict]:
    catalogo: list[dict] = []
    vistos: set[str] = set()

    for trabalho in trabalhos_brutos:
        titulo = normalizar_texto(trabalho.get("titulo"))
        if not titulo:
            continue

        ano = normalizar_ano(trabalho.get("ano"))
        id_trabalho = gerar_id("trabalho_ic", titulo, ano)
        if id_trabalho in vistos:
            continue
        vistos.add(id_trabalho)

        catalogo.append(
            {
                "id": id_trabalho,
                "titulo": titulo,
                "autores": normalizar_texto(trabalho.get("autores")),
                "resumo": normalizar_texto(trabalho.get("resumo")) or None,
                "palavrasChaves": trabalho.get("palavrasChaves", []),
                "ano": ano,
            }
        )

    return catalogo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Limpa o catálogo de trabalhos de IC/periódicos na camada Silver."
    )
    parser.add_argument("--trabalhos-ic", default=DEFAULT_TRABALHOS_IC)
    parser.add_argument("--saida", default=DEFAULT_SAIDA)
    args = parser.parse_args()

    trabalhos_brutos = ler_json_bronze(args.trabalhos_ic)
    catalogo = limpar_trabalhos(trabalhos_brutos)

    if not catalogo:
        print("Nenhum trabalho de IC/periódico válido encontrado; nada gravado na Silver.")
        return

    salvar_parquet_silver(args.saida, catalogo)
    print(f"Trabalhos de IC/periódicos limpos: {len(catalogo)}.")
    print(f"Parquet salvo em: silver/{args.saida}")


if __name__ == "__main__":
    main()
