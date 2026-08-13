#!/usr/bin/env python3
"""Web scraping de professores do SIGAA (camada Bronze)."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DEFAULT_URL = (
    "https://sigaa.unifei.edu.br/sigaa/public/departamento/professores.jsf?id=127"
)
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT_DIR / "data" / "bronze" / "sigaa" / "professores.json"
TAMANHO_ID_LATTES = len("8122238750933560")
ID_LATTES_NUMERICO = re.compile(r"lattes\.cnpq\.br/(\d+)", re.IGNORECASE)


def normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def limpar_nome(nome: str) -> str:
    return re.sub(
        r"\s*\((?:DOUTOR|MESTRE)\)\s*$",
        "",
        nome,
        flags=re.IGNORECASE,
    ).strip()


def extrair_id_lattes(url: str) -> str | None:
    match = ID_LATTES_NUMERICO.search(url)
    return match.group(1) if match else None


def id_lattes_valido(id_lattes: str) -> bool:
    return id_lattes.isdigit() and len(id_lattes) == TAMANHO_ID_LATTES


def validar_endereco_lattes(url: str | None) -> str | None:
    if not url:
        return None

    id_lattes = extrair_id_lattes(url)
    if id_lattes is None or not id_lattes_valido(id_lattes):
        return None

    return url


def extrair_professores(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    professores: list[dict[str, str | None]] = []

    for celula in soup.select("td.descricao"):
        nome_el = celula.select_one("span.nome")
        if nome_el is None:
            continue

        nome = limpar_nome(normalizar_texto(nome_el.get_text()))

        lattes_el = celula.select_one("span.enderecoLattes a[href]")
        endereco_lattes = validar_endereco_lattes(
            lattes_el["href"].strip() if lattes_el else None
        )

        professores.append(
            {
                "nome": nome,
                "enderecoLattes": endereco_lattes,
            }
        )

    return professores


def buscar_html(url: str, timeout: int = 30) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; TCC-Bronze-Scraper/1.0; "
                "+https://sigaa.unifei.edu.br)"
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
        description="Extrai nome e enderecoLattes dos professores do SIGAA."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL da página do departamento.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Arquivo JSON de saída.",
    )
    args = parser.parse_args()

    html = buscar_html(args.url)
    professores = extrair_professores(html)

    if not professores:
        raise RuntimeError("Nenhum professor encontrado. Verifique a estrutura da página.")

    salvar_json(professores, args.output)

    com_lattes = sum(1 for professor in professores if professor["enderecoLattes"])
    print(f"Extraídos {len(professores)} professores ({com_lattes} com Lattes).")
    print(f"Arquivo salvo em: {args.output}")
    print(f"Coletado em: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
