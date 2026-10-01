#!/usr/bin/env python3
"""Orquestra a camada Gold: perfis Parquet da Silver para perfis JSON unificados na Gold."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
GOLD_DIR = ROOT_DIR / "gold"


def executar_etapa(nome: str, comando: list[str]) -> None:
    print(f"\n=== {nome} ===")
    resultado = subprocess.run(comando, cwd=GOLD_DIR, check=False)
    if resultado.returncode != 0:
        raise RuntimeError(f"Etapa '{nome}' falhou com código {resultado.returncode}.")


def main() -> None:
    python = sys.executable
    executar_etapa(
        "Unificar perfis SIGAA + Lattes",
        [python, "unificar_perfis.py"],
    )
    print("\nPipeline Gold concluído.")


if __name__ == "__main__":
    main()
