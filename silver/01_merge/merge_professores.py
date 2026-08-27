#!/usr/bin/env python3
"""Faz merge dos professores extraídos do SIGAA e do site do IESTI."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
LEGACY_SIGAA = ROOT_DIR / "data" / "bronze" / "sigaa" / "professores.json"
LEGACY_IESTI = ROOT_DIR / "data" / "bronze" / "iesti_site" / "professores.json"
DEFAULT_SIGAA = ROOT_DIR / "data" / "bronze" / "raw" / "sigaa" / "professores_sigaa.json"
DEFAULT_IESTI = ROOT_DIR / "data" / "bronze" / "raw" / "iesti_site" / "professores_iesti_site.json"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "bronze" / "merged" / "professores_sigaa_iesti_merged.json"
LEGACY_OUTPUT = ROOT_DIR / "data" / "bronze" / "merged" / "professores.json"
TAMANHO_ID_LATTES = len("8122238750933560")
ID_LATTES_NUMERICO = re.compile(r"lattes\.cnpq\.br/(\d+)", re.IGNORECASE)
LIMIAR_SIMILARIDADE = 0.92


@dataclass
class Professor:
    nome: str
    id_lattes: str | None = None
    siape: str | None = None
    url_portal_sigaa: str | None = None
    fontes: set[str] = field(default_factory=set)


def normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_nome(nome: str) -> str:
    nome = normalizar_texto(nome)
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(char for char in nome if not unicodedata.combining(char))
    nome = nome.upper()
    nome = re.sub(r"[`'´’‘]", "'", nome)
    return nome


def chave_nome(nome: str) -> str:
    chave = normalizar_nome(nome)
    chave = re.sub(r"\bDE\b", "", chave)
    chave = re.sub(r"[^A-Z0-9' ]+", "", chave)
    return re.sub(r"\s+", " ", chave).strip()


def extrair_id_lattes_de_url(url: str | None) -> str | None:
    if not url:
        return None

    match = ID_LATTES_NUMERICO.search(url)
    if not match:
        return None

    id_lattes = match.group(1)
    if id_lattes.isdigit() and len(id_lattes) == TAMANHO_ID_LATTES:
        return id_lattes

    return None


def id_lattes_valido(id_lattes: str | None) -> bool:
    return bool(id_lattes and id_lattes.isdigit() and len(id_lattes) == TAMANHO_ID_LATTES)


def similaridade_nomes(nome_a: str, nome_b: str) -> float:
    return SequenceMatcher(None, chave_nome(nome_a), chave_nome(nome_b)).ratio()


def escolher_nome(nome_atual: str, nome_novo: str) -> str:
    if len(normalizar_nome(nome_novo)) > len(normalizar_nome(nome_atual)):
        return nome_novo
    return nome_atual


def carregar_sigaa(caminho: Path) -> list[Professor]:
    with caminho.open(encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    professores: list[Professor] = []
    for item in dados:
        professores.append(
            Professor(
                nome=normalizar_nome(item["nome"]),
                id_lattes=extrair_id_lattes_de_url(item.get("enderecoLattes")),
                siape=item.get("siape"),
                url_portal_sigaa=item.get("urlPortalSigaa"),
                fontes={"sigaa"},
            )
        )

    return professores


def carregar_iesti(caminho: Path) -> list[Professor]:
    with caminho.open(encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

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


def salvar_json(professores: list[Professor], caminho: Path) -> None:
    dados = [
        {
            "nome": professor.nome,
            "idLattes": professor.id_lattes,
            "siape": professor.siape,
            "urlPortalSigaa": professor.url_portal_sigaa,
        }
        for professor in professores
    ]

    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mescla professores do SIGAA e do site do IESTI em um único JSON."
    )
    parser.add_argument("--sigaa", type=Path, default=DEFAULT_SIGAA)
    parser.add_argument("--iesti", type=Path, default=DEFAULT_IESTI)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    sigaa_path = args.sigaa
    if not sigaa_path.exists() and LEGACY_SIGAA.exists():
        sigaa_path = LEGACY_SIGAA

    iesti_path = args.iesti
    if not iesti_path.exists() and LEGACY_IESTI.exists():
        iesti_path = LEGACY_IESTI

    if not sigaa_path.exists():
        raise FileNotFoundError(f"Arquivo SIGAA não encontrado: {sigaa_path}")

    professores = fazer_merge(carregar_sigaa(sigaa_path), carregar_iesti(iesti_path))
    salvar_json(professores, args.output)

    com_lattes = sum(1 for professor in professores if professor.id_lattes)
    print(f"Merge concluído: {len(professores)} professores ({com_lattes} com idLattes).")
    print(f"Arquivo salvo em: {args.output}")


if __name__ == "__main__":
    main()
