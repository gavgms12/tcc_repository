#!/usr/bin/env python3
"""Pipeline da camada Bronze: coleta os dados brutos das fontes públicas.

Chama diretamente as funções de coleta (as mesmas usadas pelas DAGs do
Airflow), de modo que CLI e DAG percorrem exatamente o mesmo código.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.log import configurar_logging

logger = logging.getLogger(__name__)


def executar(com_ementa: bool = False, limite_docentes: int = 0) -> None:
    from bronze.scraping.scrape_professores_iesti import executar_coleta as iesti
    from bronze.scraping.scrape_professores_sigaa import executar_scraping as sigaa
    from bronze.scraping.scrape_sigaa_componentes import executar_coleta as componentes
    from bronze.scraping.scrape_sigaa_docente import executar_coleta as docentes
    from bronze.scraping.scrape_trabalhos_ic import executar_coleta as trabalhos_ic

    etapas = [
        ("Scraping SIGAA", lambda: sigaa()),
        ("Componentes SIGAA", lambda: componentes(com_ementa=com_ementa)),
        ("Docentes SIGAA", lambda: docentes(limite=limite_docentes)),
        ("Scraping IESTI", lambda: iesti()),
        ("Scraping periódicos", lambda: trabalhos_ic()),
    ]
    for nome, etapa in etapas:
        logger.info("=== %s ===", nome)
        etapa()

    logger.info("Camada Bronze concluída: os JSONs brutos foram enviados ao MinIO.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa a coleta da camada Bronze.")
    parser.add_argument(
        "--com-ementa",
        action="store_true",
        help="Busca ementa dos componentes curriculares sem ementa conhecida.",
    )
    parser.add_argument(
        "--limite-docentes",
        type=int,
        default=0,
        help="Limita coleta detalhada de docentes no SIGAA (0 = todos).",
    )
    args = parser.parse_args()
    configurar_logging()
    executar(com_ementa=args.com_ementa, limite_docentes=args.limite_docentes)


if __name__ == "__main__":
    main()
