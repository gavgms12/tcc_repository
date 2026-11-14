"""Extração e validação de identificadores do Currículo Lattes."""

from __future__ import annotations

import re

TAMANHO_ID_LATTES = 16
ID_LATTES_NUMERICO = re.compile(r"lattes\.cnpq\.br/(\d+)", re.IGNORECASE)


def extrair_id_lattes(url: str | None) -> str | None:
    if not url:
        return None
    match = ID_LATTES_NUMERICO.search(url)
    return match.group(1) if match else None


def id_lattes_valido(id_lattes: str | None) -> bool:
    return bool(
        id_lattes and id_lattes.isdigit() and len(id_lattes) == TAMANHO_ID_LATTES
    )


def validar_id_lattes(url: str | None) -> str | None:
    """Extrai o id Lattes de uma URL e o devolve só se for válido."""
    id_lattes = extrair_id_lattes(url)
    return id_lattes if id_lattes_valido(id_lattes) else None
