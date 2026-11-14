#!/usr/bin/env python3
"""Pipeline da camada Gold: perfis Parquet da Silver para perfis JSON unificados."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.log import configurar_logging
from gold.unificar_perfis import executar_unificacao

logger = logging.getLogger(__name__)


def main() -> None:
    configurar_logging()
    executar_unificacao()
    logger.info("Pipeline Gold concluído.")


if __name__ == "__main__":
    main()
