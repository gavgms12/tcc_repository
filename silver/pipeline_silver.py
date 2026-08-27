#!/usr/bin/env python3
"""Orquestra a camada Silver."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BRONZE_DIR = ROOT_DIR / "bronze"
SILVER_DIR = ROOT_DIR / "silver"
SCRIPTLATTES_DIR = ROOT_DIR.parent / "scriptLattes"
SCRIPTLATTES_CONFIG = SCRIPTLATTES_DIR / "exemplo" / "teste-02.config"


def executar_etapa(nome: str, comando: list[str], cwd: Path | None = None) -> None:
    print(f"\n=== {nome} ===")
    resultado = subprocess.run(comando, cwd=cwd or SILVER_DIR, check=False)
    if resultado.returncode != 0:
        raise RuntimeError(f"Etapa '{nome}' falhou com código {resultado.returncode}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa o pipeline da camada Silver.")
    parser.add_argument("--skip-merge", action="store_true", help="Pula o merge SIGAA + IESTI.")
    parser.add_argument("--skip-lista", action="store_true", help="Pula a geração da lista para o scriptLattes.")
    parser.add_argument("--skip-lattes", action="store_true", help="Pula a coleta de currículos pelo scriptLattes.")
    parser.add_argument("--skip-integracao", action="store_true", help="Pula a etapa de integração com Lattes.")
    args = parser.parse_args()

    python = sys.executable

    if not args.skip_merge:
        executar_etapa(
            "Merge SIGAA + IESTI",
            [python, "01_merge/merge_professores.py"],
        )

    if not args.skip_lista:
        executar_etapa(
            "Gerar lista para Lattes",
            [python, "01_merge/gerar_lista_scriptlattes.py"],
        )

    if not args.skip_lattes:
        venv_python = SCRIPTLATTES_DIR / "venv" / "bin" / "python"
        if not venv_python.exists():
            raise FileNotFoundError(
                f"venv do scriptLattes não encontrada em {venv_python}. "
                "Execute 'make install' no repositório scriptLattes."
            )
        if not SCRIPTLATTES_CONFIG.is_file():
            raise FileNotFoundError(f"Config não encontrado: {SCRIPTLATTES_CONFIG}")
        executar_etapa(
            "scriptLattes",
            [str(venv_python), str(SCRIPTLATTES_DIR / "scriptLattes.py"), str(SCRIPTLATTES_CONFIG)],
            cwd=SCRIPTLATTES_DIR,
        )

    if not args.skip_integracao:
        executar_etapa(
            "Vincular disciplinas",
            [python, "02_integracao/vincular_disciplinas.py", "--buscar-ementa-vinculadas"],
        )
        executar_etapa(
            "Vincular trabalhos IC",
            [python, "02_integracao/vincular_ics.py", "--buscar-ics-vinculadas"],
        )
        executar_etapa(
            "Transformar Lattes",
            [python, "02_integracao/transformar_lattes.py"],
        )
        executar_etapa(
            "Unir Lattes + SIGAA",
            [python, "02_integracao/unir_lattes_sigaa.py"],
        )

    print("\nPipeline Silver concluído.")


if __name__ == "__main__":
    main()
