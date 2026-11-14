#!/usr/bin/env python3
"""Faz merge dos professores extraídos do SIGAA e do site do IESTI."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.lattes import id_lattes_valido, validar_id_lattes
from common.log import configurar_logging
from common.texto import normalizar_nome as _normalizar_nome_comum
from storage.minio_storage import ler_json_bronze_recente, salvar_parquet_silver

logger = logging.getLogger(__name__)

DEFAULT_SIGAA = "raw/sigaa/professores_sigaa.json"
DEFAULT_IESTI = "raw/iesti_site/professores_iesti_site.json"
DEFAULT_OUTPUT = "professores_unificados.parquet"
LIMIAR_SIMILARIDADE = 0.92


@dataclass
class Professor:
    nome: str
    id_lattes: str | None = None
    siape: str | None = None
    url_portal_sigaa: str | None = None
    fontes: set[str] = field(default_factory=set)


def normalizar_nome(nome: str) -> str:
    """Nome comparável entre fontes: maiúsculas, sem acentos e com um único
    tipo de apóstrofo (D'ÁVILA / D´AVILA / D`AVILA)."""
    return re.sub(r"[`'´’‘]", "'", _normalizar_nome_comum(nome))


def chave_nome(nome: str) -> str:
    chave = normalizar_nome(nome)
    chave = re.sub(r"\bDE\b", "", chave)
    chave = re.sub(r"[^A-Z0-9' ]+", "", chave)
    return re.sub(r"\s+", " ", chave).strip()


def similaridade_nomes(nome_a: str, nome_b: str) -> float:
    return SequenceMatcher(None, chave_nome(nome_a), chave_nome(nome_b)).ratio()


def escolher_nome(nome_atual: str, nome_novo: str) -> str:
    if len(normalizar_nome(nome_novo)) > len(normalizar_nome(nome_atual)):
        return nome_novo
    return nome_atual


def carregar_sigaa(chave: str) -> list[Professor]:
    dados = ler_json_bronze_recente(chave)

    professores: list[Professor] = []
    for item in dados:
        professores.append(
            Professor(
                nome=normalizar_nome(item["nome"]),
                id_lattes=validar_id_lattes(item.get("enderecoLattes")),
                siape=item.get("siape"),
                url_portal_sigaa=item.get("urlPortalSigaa"),
                fontes={"sigaa"},
            )
        )

    return professores


def carregar_iesti(chave: str) -> list[Professor]:
    dados = ler_json_bronze_recente(chave)

    professores: list[Professor] = []
    for item in dados:
        id_lattes = item.get("idLattes")
        if not id_lattes_valido(id_lattes):
            id_lattes = None

        professores.append(
            Professor(
                nome=normalizar_nome(item["nome"]),
                id_lattes=id_lattes,
                fontes={"iesti"},
            )
        )

    return professores


def buscar_indice_por_similaridade(
    professor: Professor, indice: dict[str, int], professores: list[Professor]
) -> int | None:
    melhor_indice: int | None = None
    melhor_score = 0.0

    for indice_existente, professor_existente in enumerate(professores):
        score = similaridade_nomes(professor.nome, professor_existente.nome)
        if score >= LIMIAR_SIMILARIDADE and score > melhor_score:
            melhor_score = score
            melhor_indice = indice_existente

    if melhor_indice is not None:
        return melhor_indice

    chave = chave_nome(professor.nome)
    return indice.get(chave)


def mesclar_professor(atual: Professor, novo: Professor) -> None:
    atual.nome = escolher_nome(atual.nome, novo.nome)
    atual.fontes.update(novo.fontes)

    if novo.id_lattes and not atual.id_lattes:
        atual.id_lattes = novo.id_lattes
    elif novo.id_lattes and atual.id_lattes and novo.id_lattes != atual.id_lattes:
        if "iesti" in novo.fontes:
            atual.id_lattes = novo.id_lattes

    if novo.siape and not atual.siape:
        atual.siape = novo.siape
    if novo.url_portal_sigaa and not atual.url_portal_sigaa:
        atual.url_portal_sigaa = novo.url_portal_sigaa


def adicionar_ou_mesclar(
    professor: Professor,
    professores: list[Professor],
    indice: dict[str, int],
) -> None:
    indice_existente = buscar_indice_por_similaridade(professor, indice, professores)

    if indice_existente is None:
        indice[chave_nome(professor.nome)] = len(professores)
        professores.append(professor)
        return

    mesclar_professor(professores[indice_existente], professor)
    indice[chave_nome(professores[indice_existente].nome)] = indice_existente


def fazer_merge(sigaa: list[Professor], iesti: list[Professor]) -> list[Professor]:
    professores: list[Professor] = []
    indice: dict[str, int] = {}

    for professor in sigaa:
        adicionar_ou_mesclar(professor, professores, indice)

    for professor in iesti:
        adicionar_ou_mesclar(professor, professores, indice)

    professores.sort(key=lambda professor: professor.nome)
    return professores


def salvar_parquet(professores: list[Professor], chave: str) -> None:
    dados = [
        {
            "nome": professor.nome,
            "idLattes": professor.id_lattes,
            "siape": professor.siape,
            "urlPortalSigaa": professor.url_portal_sigaa,
        }
        for professor in professores
    ]

    salvar_parquet_silver(chave, dados)


def executar_merge(
    sigaa: str = DEFAULT_SIGAA,
    iesti: str = DEFAULT_IESTI,
    output: str = DEFAULT_OUTPUT,
) -> None:
    """Função utilizada pelo Airflow e pela CLI."""
    professores = fazer_merge(carregar_sigaa(sigaa), carregar_iesti(iesti))
    salvar_parquet(professores, output)

    com_lattes = sum(1 for professor in professores if professor.id_lattes)
    logger.info(
        "Merge concluído: %d professores (%d com idLattes).",
        len(professores),
        com_lattes,
    )
    logger.info("Objeto Parquet salvo em: silver/%s", output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mescla professores Bronze e grava o resultado em Parquet na Silver."
    )
    parser.add_argument("--sigaa", default=DEFAULT_SIGAA, help="Chave Bronze do SIGAA.")
    parser.add_argument("--iesti", default=DEFAULT_IESTI, help="Chave Bronze do IESTI.")
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT, help="Chave Parquet no bucket Silver."
    )
    args = parser.parse_args()
    configurar_logging()

    executar_merge(sigaa=args.sigaa, iesti=args.iesti, output=args.output)


if __name__ == "__main__":
    main()
