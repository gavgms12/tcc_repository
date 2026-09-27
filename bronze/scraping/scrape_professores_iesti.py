#!/usr/bin/env python3
"""Web scraping do corpo docente do site do IESTI (camada Bronze)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bronze.scraping.utils import buscar_html, criar_sessao, normalizar_nome, validar_id_lattes
from storage.minio_storage import salvar_json_bronze

DEFAULT_URL = "https://iesti.unifei.edu.br/corpo-docente/"
DEFAULT_OUTPUT = "raw/iesti_site/professores_iesti_site.json"


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

        professores.append(
            {
                "nome": nome,
                "idLattes": validar_id_lattes(endereco_lattes),
            }
        )

    return professores


def executar_coleta(
    url: str = DEFAULT_URL,
    output: str = DEFAULT_OUTPUT,
    verify_ssl: bool = False,
) -> None:
    """Função utilizada pelo Airflow e pela CLI."""
    session = criar_sessao()
    html = buscar_html(session, url, verify=verify_ssl)
    professores = extrair_professores(html)

    if not professores:
        raise RuntimeError("Nenhum professor encontrado. Verifique a estrutura da página.")

    salvar_json_bronze(output, professores)

    com_lattes = sum(1 for professor in professores if professor["idLattes"])
    print(f"Extraídos {len(professores)} professores ({com_lattes} com idLattes).")
    print(f"Objeto salvo em: bronze/{output}")
    print(f"Coletado em: {datetime.now(timezone.utc).isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai nome e idLattes do corpo docente do site do IESTI."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL da página do IESTI.")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Chave do objeto JSON no bucket Bronze.",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Valida o certificado SSL do site (desativado por padrão).",
    )
    args = parser.parse_args()

    executar_coleta(url=args.url, output=args.output, verify_ssl=args.verify_ssl)


if __name__ == "__main__":
    main()
