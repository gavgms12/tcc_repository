#!/usr/bin/env python3
"""Pipeline da camada Silver: Bronze (MinIO) para Parquet (MinIO).

Chama as mesmas funções usadas pelas DAGs do Airflow, sem subprocess.
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


def executar(
    skip_merge: bool = False,
    skip_lattes: bool = False,
    limite_lattes: int = 0,
    skip_limpeza: bool = False,
) -> None:
    from silver.integracao.executar_scriptlattes import executar_lattes
    from silver.integracao.limpar_perfis import executar_limpeza
    from silver.merge.merge_professores import executar_merge

    if not skip_merge:
        logger.info("=== Unificar professores e gravar Parquet ===")
        executar_merge()

    if not skip_lattes:
        logger.info("=== Extrair currículos Lattes ===")
        executar_lattes(limite=limite_lattes)

    if not skip_limpeza:
        logger.info("=== Limpar perfis SIGAA e Lattes ===")
        executar_limpeza()

    logger.info("Pipeline Silver concluído.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lê os dados Bronze do MinIO e gera Parquet na camada Silver."
    )
    parser.add_argument(
        "--skip-merge", action="store_true", help="Pula o merge SIGAA + IESTI."
    )
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
        "--skip-limpeza",
        action="store_true",
        help="Pula a limpeza dos perfis SIGAA e Lattes.",
    )
    args = parser.parse_args()
    configurar_logging()
    executar(
        skip_merge=args.skip_merge,
        skip_lattes=args.skip_lattes,
        limite_lattes=args.limite_lattes,
        skip_limpeza=args.skip_limpeza,
    )


if __name__ == "__main__":
    main()
