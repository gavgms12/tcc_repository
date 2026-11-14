"""Configuração de logging usada pelas CLIs; o Airflow já configura o dele."""

from __future__ import annotations

import logging
import sys


def configurar_logging(nivel: int = logging.INFO) -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=nivel,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
