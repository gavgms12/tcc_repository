#!/usr/bin/env python3
"""Exporta os Parquets da Silver (MinIO) para JSON legível em disco.

Serve pra conferir visualmente os dados de cada etapa da Silver (perfis SIGAA
e Lattes limpos, catálogos de componentes, roster de identidade) num editor
de texto comum, sem precisar abrir o Parquet num notebook.

Exemplos:
    # exporta todos os arquivos conhecidos da Silver para data/silver/json/
    python silver/exportar_json.py

    # exporta só um arquivo específico
    python silver/exportar_json.py perfis_lattes_limpos.parquet

    # exporta pra outra pasta
    python silver/exportar_json.py --saida-dir /tmp/conferencia
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from botocore.exceptions import ClientError

from storage.minio_storage import ler_parquet_silver

ARQUIVOS_CONHECIDOS = [
    "professores_unificados.parquet",
    "perfis_sigaa_limpos.parquet",
    "perfis_lattes_limpos.parquet",
    "componentes_curriculares.parquet",
    "componentes_curriculares_externos.parquet",
    "trabalhos_ic_periodicos.parquet",
]

DEFAULT_SAIDA_DIR = ROOT_DIR / "data" / "silver" / "json"


def chave_ausente(erro: ClientError) -> bool:
    codigo = str(erro.response.get("Error", {}).get("Code", ""))
    return codigo in {"404", "NoSuchKey"}


def exportar_arquivo(chave: str, saida_dir: Path) -> Path | None:
    try:
        registros = ler_parquet_silver(chave)
    except ClientError as erro:
        if chave_ausente(erro):
            print(f"  (pulado) {chave}: ainda não existe no bucket silver.")
            return None
        raise

    saida_dir.mkdir(parents=True, exist_ok=True)
    destino = saida_dir / chave.replace(".parquet", ".json")
    destino.write_text(
        json.dumps(registros, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  {chave}: {len(registros)} registro(s) -> {destino}")
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporta Parquets da Silver (MinIO) para JSON legível em disco."
    )
    parser.add_argument(
        "chaves",
        nargs="*",
        help=(
            "Arquivos específicos a exportar (ex.: perfis_lattes_limpos.parquet). "
            "Sem argumento, exporta todos os arquivos conhecidos da Silver."
        ),
    )
    parser.add_argument(
        "--saida-dir",
        default=str(DEFAULT_SAIDA_DIR),
        help=f"Pasta de destino dos JSONs (padrão: {DEFAULT_SAIDA_DIR}).",
    )
    args = parser.parse_args()

    chaves = args.chaves or ARQUIVOS_CONHECIDOS
    saida_dir = Path(args.saida_dir)

    print(f"Exportando para: {saida_dir.resolve()}\n")
    exportados = 0
    for chave in chaves:
        if exportar_arquivo(chave, saida_dir) is not None:
            exportados += 1

    print(f"\n{exportados} de {len(chaves)} arquivo(s) exportado(s).")


if __name__ == "__main__":
    main()
