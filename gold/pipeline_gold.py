#!/usr/bin/env python3
"""Orquestra a camada Gold: Parquet Silver (MinIO) para perfis unificados (MinIO)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
GOLD_DIR = ROOT_DIR / "gold"


def executar_etapa(nome: str, comando: list[str], cwd: Path | None = None) -> None:
    print(f"\n=== {nome} ===")
    resultado = subprocess.run(comando, cwd=cwd or GOLD_DIR, check=False)
    if resultado.returncode != 0:
        raise RuntimeError(f"Etapa '{nome}' falhou com código {resultado.returncode}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lê os Parquets já limpos da Silver e grava os perfis unificados na Gold."
    )
    parser.parse_args()

    python = sys.executable
    executar_etapa(
        "Unificar perfis SIGAA + Lattes",
        [python, "01_unificacao/unificar_perfis.py"],
    )

    print("\nPipeline Gold concluído.")


if __name__ == "__main__":
    main()
