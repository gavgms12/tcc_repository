"""Reduz os resumos dos docentes ao que descreve a atuação deles.

A limpeza é conservadora: uma frase só sai do resumo se tratar apenas de
titulação ou de cargo atual. Na dúvida, a frase fica, e sinais de conteúdo como
área, ênfase ou temas a mantêm inteira. Não há corte por tamanho. As frases de titulação são devolvidas à parte, para virarem
formação quando o SIGAA não a informa, e o texto original fica na Silver.
"""

from __future__ import annotations

import re
from typing import TypedDict

from common.texto import chave_frase, dividir_frases, normalizar_texto

_OUTRO_IDIOMA = re.compile(
    r"\b(?:English|Ingl[eê]s|Deutsch|Alem[aã]o|Espa[nñ]ol|Fran[cç]ais|Abstract)\s*:",
    re.IGNORECASE,
)
_MARCADOR_PORTUGUES = re.compile(r"\bPortugu[eê]s\s*:\s*", re.IGNORECASE)
# Titulação e cargo só contam no início da frase: "Durante o mestrado, aprofundei
# meus estudos em..." descreve atuação, não titulação.
_TITULACAO = re.compile(
    r"^(?:(?:é|possui|tem|concluiu(?: o)?)\s+)?"
    r"(?:graduou-se|graduad[oa]|gradua[cç][aã]o|bacharel(?:ado)?"
    r"|mestr(?:e|ado)|doutor(?:a|ado)?|p[oó]s-doutorado|licenciatura|t[eé]cnico em)\b"
    r"|\brecebeu os graus\b",
    re.IGNORECASE,
)
_CARGO = re.compile(
    r"^(?:atualmente,?\s+)?(?:é\s+|sou\s+|atua como\s+)?"
    r"(?:professor(?:a)?|docente|titular)\b",
    re.IGNORECASE,
)
_MAX_PALAVRAS_CARGO = 14
_CONTEUDO = re.compile(
    r"\b(?:[aá]reas?|[eê]nfase|atu(?:a|am|ar|ando|ou|a[cç][aã]o|a[cç][oõ]es)"
    r"|experi[eê]ncias?|pesquisas?|temas?|interesses?|especializa\w*|leciona\w*"
    r"|projetos?|desenvolv\w*|laborat[oó]rio\w*|grupos?|linhas?"
    r"|concentra[cç][aã]o|tese|disserta[cç][aã]o|sobre|foco)\b",
    re.IGNORECASE,
)
# Numa frase de titulação, nomes como "Fundação de Ensino e Pesquisa" não contam:
# só a indicação explícita do assunto do título mantém a frase no resumo.
_CONTEUDO_DA_TITULACAO = re.compile(
    r"\b(?:[eê]nfase em|[aá]reas? de|especializa[cç][aã]o em \w+ de|pesquisa na|sobre)\b",
    re.IGNORECASE,
)


class ResumoSeparado(TypedDict):
    essencial: str | None
    titulacao: str | None


def separar_resumo(texto: str | None) -> ResumoSeparado:
    """Separa o que descreve a atuação das frases só de titulação.

    Também descarta traduções marcadas ("English: ..."), frases repetidas e
    frases só de cargo, sem conteúdo sobre a atuação.
    """
    texto = normalizar_texto(texto)
    marcador = _OUTRO_IDIOMA.search(texto)
    if marcador:
        texto = texto[: marcador.start()]
    texto = _MARCADOR_PORTUGUES.sub("", texto)

    essenciais: list[str] = []
    titulacao: list[str] = []
    vistas: set[str] = set()
    for frase in dividir_frases(texto):
        chave = chave_frase(frase)
        if not chave or chave in vistas:
            continue
        vistas.add(chave)
        if _TITULACAO.search(frase):
            if _CONTEUDO_DA_TITULACAO.search(frase):
                essenciais.append(frase)
            else:
                titulacao.append(frase)
        elif (
            _CARGO.search(frase)
            and not _CONTEUDO.search(frase)
            and len(frase.split()) <= _MAX_PALAVRAS_CARGO
        ):
            continue
        else:
            essenciais.append(frase)

    return {
        "essencial": " ".join(essenciais).rstrip(".").strip() or None,
        "titulacao": " ".join(titulacao).strip() or None,
    }
