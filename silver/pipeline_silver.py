#!/usr/bin/env python3
"""Orquestra a camada Silver: Bronze (MinIO) para Parquet (MinIO)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BRONZE_DIR = ROOT_DIR / "bronze"
SILVER_DIR = ROOT_DIR / "silver"


def executar_etapa(nome: str, comando: list[str], cwd: Path | None = None) -> None:
    print(f"\n=== {nome} ===")
    resultado = subprocess.run(comando, cwd=cwd or SILVER_DIR, check=False)
    if resultado.returncode != 0:
        raise RuntimeError(f"Etapa '{nome}' falhou com código {resultado.returncode}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lê os dados Bronze do MinIO e gera Parquet na camada Silver."
    )
    parser.add_argument("--skip-merge", action="store_true", help="Pula o merge SIGAA + IESTI.")
    parser.add_argument(
        "--skip-lattes",
        action="store_true",
        help="Pula a extração de currículos com o scriptLattes.",
    )
    parser.add_argument(
        "--limite-lattes",
        type=int,
        default=0,
        help="Limita currículos Lattes para teste (0 = todos).",
    )
    parser.add_argument(
        "--skip-unificacao",
        action="store_true",
        help="Pula a limpeza/unificação dos perfis SIGAA + Lattes.",
    )
    args = parser.parse_args()

    python = sys.executable

    if not args.skip_merge:
        executar_etapa(
            "Unificar professores e gravar Parquet",
            [python, "01_merge/merge_professores.py"],
        )

    if not args.skip_lattes:
        comando_lattes = [python, "02_integracao/executar_scriptlattes.py"]
        if args.limite_lattes > 0:
            comando_lattes.extend(["--limite", str(args.limite_lattes)])
        executar_etapa("Extrair currículos Lattes", comando_lattes)

    if not args.skip_unificacao:
        executar_etapa(
            "Unificar perfis SIGAA + Lattes",
            [python, "02_integracao/unificar_perfis.py"],
        )

    print("\nPipeline Silver concluído.")


if __name__ == "__main__":
    main()
