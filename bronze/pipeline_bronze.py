#!/usr/bin/env python3
"""Pipeline da camada Bronze: coleta os dados brutos das fontes públicas."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BRONZE_DIR = Path(__file__).resolve().parent
TCC_ROOT = BRONZE_DIR.parent


def executar_etapa(nome: str, comando: list[str], cwd: Path | None = None) -> None:
    print(f"\n=== {nome} ===")
    resultado = subprocess.run(comando, cwd=cwd or BRONZE_DIR, check=False)
    if resultado.returncode != 0:
        raise RuntimeError(f"Etapa '{nome}' falhou com código {resultado.returncode}.")


def verificar_dependencias() -> None:
    faltando: list[str] = []
    try:
        import requests  # noqa: F401
    except ImportError:
        faltando.append("requests")
    try:
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError:
        faltando.append("beautifulsoup4")
    if faltando:
        print(
            "Dependências ausentes: "
            + ", ".join(faltando)
            + "\n\nAtive a venv do projeto (tcc_code/venv) e instale:\n"
            "  cd tcc_code && source venv/bin/activate\n"
            "  pip install -r bronze/requirements.txt\n\n"
            "Não use a venv do scriptLattes para os scripts Bronze.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    verificar_dependencias()
    parser = argparse.ArgumentParser(description="Executa a coleta da camada Bronze.")
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Pula a coleta e usa os arquivos brutos já existentes.",
    )
    parser.add_argument(
        "--com-ementa",
        action="store_true",
        help="Busca ementa de todos os componentes curriculares (mais lento).",
    )
    parser.add_argument(
        "--limite-docentes",
        type=int,
        default=0,
        help="Limita coleta detalhada de docentes no SIGAA (0 = todos).",
    )
    args = parser.parse_args()

    python = sys.executable

    if not args.skip_scraping:
        executar_etapa(
            "Scraping SIGAA", [python, "scraping/scrape_professores_sigaa.py"]
        )

        comando_componentes = [python, "scraping/scrape_sigaa_componentes.py"]
        if args.com_ementa:
            comando_componentes.append("--com-ementa")
        executar_etapa("Componentes SIGAA", comando_componentes)

        comando_docentes = [python, "scraping/scrape_sigaa_docente.py"]
        if args.limite_docentes > 0:
            comando_docentes.extend(["--limite", str(args.limite_docentes)])
        executar_etapa("Docentes SIGAA", comando_docentes)

        executar_etapa(
            "Scraping IESTI", [python, "scraping/scrape_professores_iesti.py"]
        )
        executar_etapa(
            "Scraping periodicos", [python, "scraping/scrape_trabalhos_ic.py"]
        )

    print("\nCamada Bronze concluída: os JSONs brutos foram enviados ao MinIO.")


if __name__ == "__main__":
    main()
