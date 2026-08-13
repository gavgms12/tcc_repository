#!/usr/bin/env python3
"""Web scraping do corpo docente do site do IESTI (camada Bronze)."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

DEFAULT_URL = "https://iesti.unifei.edu.br/corpo-docente/"
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT_DIR / "data" / "bronze" / "iesti_site" / "professores.json"
TAMANHO_ID_LATTES = len("8122238750933560")
ID_LATTES_NUMERICO = re.compile(r"lattes\.cnpq\.br/(\d+)", re.IGNORECASE)


def normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_nome(nome: str) -> str:
    nome = normalizar_texto(nome)
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(char for char in nome if not unicodedata.combining(char))
    return nome.upper()


def extrair_id_lattes(url: str) -> str | None:
    match = ID_LATTES_NUMERICO.search(url)
    return match.group(1) if match else None


def id_lattes_valido(id_lattes: str) -> bool:
    return id_lattes.isdigit() and len(id_lattes) == TAMANHO_ID_LATTES


def validar_id_lattes(url: str | None) -> str | None:
    if not url:
        return None

    id_lattes = extrair_id_lattes(url)
    if id_lattes is None or not id_lattes_valido(id_lattes):
        return None

    return id_lattes


def extrair_professores(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    professores: list[dict[str, str | None]] = []

    for paragrafo in soup.find_all("p"):
        nome_el = paragrafo.find("strong")
        if nome_el is None:
            continue

        nome = normalizar_nome(nome_el.get_text())
        if len(nome) < 5:
            continue

        endereco_lattes = None
        for link in paragrafo.find_all("a", href=True):
            href = link["href"].strip()
            if "lattes.cnpq.br" in href.lower():
                endereco_lattes = href
                break

        id_lattes = validar_id_lattes(endereco_lattes)

        professores.append(
            {
                "nome": nome,
                "idLattes": id_lattes,
            }
        )

    return professores


def buscar_html(url: str, timeout: int = 30, verify_ssl: bool = False) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        verify=verify_ssl,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; TCC-Bronze-Scraper/1.0; "
                "+https://iesti.unifei.edu.br)"
            )
        },
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def salvar_json(dados: list[dict[str, str | None]], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai nome e idLattes do corpo docente do site do IESTI."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL da página do IESTI.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Arquivo JSON de saída.",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Valida o certificado SSL do site (desativado por padrão).",
    )
    args = parser.parse_args()

    if not args.verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    html = buscar_html(args.url, verify_ssl=args.verify_ssl)
    professores = extrair_professores(html)

    if not professores:
        raise RuntimeError("Nenhum professor encontrado. Verifique a estrutura da página.")

    salvar_json(professores, args.output)

    com_lattes = sum(1 for professor in professores if professor["idLattes"])
    print(f"Extraídos {len(professores)} professores ({com_lattes} com idLattes).")
    print(f"Arquivo salvo em: {args.output}")
    print(f"Coletado em: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
