"""Normalização de texto compartilhada por todas as camadas."""

from __future__ import annotations

import re
import unicodedata


def normalizar_texto(texto: str | None) -> str:
    """Colapsa espaços repetidos; `None` vira string vazia."""
    if not texto:
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip()


def normalizar_nome(nome: str) -> str:
    """Nome em maiúsculas e sem acentos, para comparação entre fontes."""
    nome = unicodedata.normalize("NFKD", normalizar_texto(nome))
    nome = "".join(char for char in nome if not unicodedata.combining(char))
    return nome.upper()
