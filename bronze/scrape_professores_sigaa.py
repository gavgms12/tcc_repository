#!/usr/bin/env python3
"""Web scraping de professores do SIGAA (camada Bronze)."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sigaa_utils import (
    BASE_URL,
    DEPARTAMENTO_ID,
    buscar_html,
    criar_sessao,
    limpar_nome,
    normalizar_texto,
    url_absoluta,
    validar_endereco_lattes,
)

DEFAULT_URL = (
    f"{BASE_URL}/sigaa/public/departamento/professores.jsf?id={DEPARTAMENTO_ID}"
)
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT_DIR / "data" / "bronze" / "sigaa" / "professores.json"
SIAPE_RE = re.compile(r"siape=(\d+)", re.IGNORECASE)


def extrair_professores(html: str) -> list[dict[str, str | None]]:
    from bs4 import BeautifulSoup

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

        portal_el = celula.select_one('span.pagina a[href*="portal.jsf"]')
        siape: str | None = None
        url_portal: str | None = None
        if portal_el and portal_el.get("href"):
            href = portal_el["href"].strip()
            match = SIAPE_RE.search(href)
            siape = match.group(1) if match else None
            url_portal = url_absoluta(href)

        professores.append(
            {
                "nome": nome,
                "siape": siape,
                "urlPortalSigaa": url_portal,
                "enderecoLattes": endereco_lattes,
            }
        )

    return professores


def salvar_json(dados: list[dict[str, str | None]], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai professores do SIGAA com siape, portal e Lattes."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL da página do departamento.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Arquivo JSON de saída.",
    )
    args = parser.parse_args()

    session = criar_sessao()
    html = buscar_html(session, args.url)
    professores = extrair_professores(html)

    if not professores:
        raise RuntimeError("Nenhum professor encontrado. Verifique a estrutura da página.")

    salvar_json(professores, args.output)

    com_lattes = sum(1 for professor in professores if professor["enderecoLattes"])
    com_siape = sum(1 for professor in professores if professor["siape"])
    print(f"Extraídos {len(professores)} professores.")
    print(f"  Com siape:  {com_siape}")
    print(f"  Com Lattes: {com_lattes}")
    print(f"Arquivo salvo em: {args.output}")
    print(f"Coletado em: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
