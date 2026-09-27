#!/usr/bin/env python3
"""Web scraping de professores do SIGAA (camada Bronze)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bronze.scraping.utils import (
    BASE_URL,
    DEPARTAMENTO_ID,
    buscar_html,
    criar_sessao,
    extrair_siape,
    limpar_nome,
    normalizar_texto,
    url_absoluta,
    validar_endereco_lattes,
)
from storage.minio_storage import salvar_json_bronze

OUTPUT_PATH = "raw/sigaa/professores_sigaa.json"
DEFAULT_URL = (
    f"{BASE_URL}/sigaa/public/departamento/professores.jsf?id={DEPARTAMENTO_ID}"
)


def extrair_professores(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    professores = []

    for celula in soup.select("td.descricao"):
        nome_el = celula.select_one("span.nome")
        if not nome_el:
            continue

        portal_el = celula.select_one('span.pagina a[href*="portal.jsf"]')
        lattes_el = celula.select_one("span.enderecoLattes a[href]")

        href_portal = portal_el.get("href", "").strip() if portal_el else None
        href_lattes = lattes_el.get("href", "").strip() if lattes_el else None

        professores.append(
            {
                "nome": limpar_nome(normalizar_texto(nome_el.get_text(strip=True))),
                "siape": extrair_siape(href_portal),
                "urlPortalSigaa": url_absoluta(href_portal) if href_portal else None,
                "enderecoLattes": validar_endereco_lattes(href_lattes),
            }
        )

    return professores


def executar_scraping(url: str = DEFAULT_URL, output: str = OUTPUT_PATH) -> None:
    """Função utilizada pelo Airflow e pela CLI."""
    session = criar_sessao()
    html = buscar_html(session, url)
    professores = extrair_professores(html)

    if not professores:
        raise RuntimeError("Nenhum professor encontrado. Verifique a estrutura da página.")

    salvar_json_bronze(output, professores)

    com_lattes = sum(1 for professor in professores if professor["enderecoLattes"])
    com_siape = sum(1 for professor in professores if professor["siape"])
    print(f"Extraídos {len(professores)} professores.")
    print(f"Com SIAPE: {com_siape}")
    print(f"Com Lattes: {com_lattes}")
    print(f"Objeto salvo em: bronze/{output}")
    print(f"Coletado em: {datetime.now(timezone.utc).isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai professores do SIGAA com siape, portal e Lattes."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL da página do departamento.")
    parser.add_argument(
        "--output", default=OUTPUT_PATH, help="Chave do objeto JSON no bucket Bronze."
    )
    args = parser.parse_args()

    executar_scraping(url=args.url, output=args.output)


if __name__ == "__main__":
    main()
