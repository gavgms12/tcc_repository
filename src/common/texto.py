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


def dividir_frases(texto: str | None) -> list[str]:
    """Divide um texto em frases, sem quebrar em iniciais como "E. E. Técnico"."""
    texto = normalizar_texto(texto)
    # Corrige ponto colado na frase seguinte ("UNIFEI.Tem sólida experiência").
    texto = re.sub(r"(\w{2,}|\))\.([A-ZÀ-Ú][a-zà-ú])", r"\1. \2", texto)
    frases: list[str] = []
    for pedaco in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú])", texto):
        if frases and re.search(r"(?:^|\s)\w\.$", frases[-1]):
            frases[-1] = f"{frases[-1]} {pedaco}"
        elif pedaco:
            frases.append(pedaco)
    return frases


def chave_frase(frase: str) -> str:
    """Forma de comparação de uma frase: minúsculas, sem pontuação."""
    return re.sub(r"\W+", " ", frase.lower()).strip()
