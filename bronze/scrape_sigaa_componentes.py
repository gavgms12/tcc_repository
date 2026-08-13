#!/usr/bin/env python3
"""Coleta componentes curriculares do departamento no SIGAA."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from sigaa_utils import (
    BASE_URL,
    DEPARTAMENTO_ID,
    buscar_html,
    criar_sessao,
    normalizar_texto,
    url_absoluta,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT_DIR / "data" / "bronze" / "sigaa" / "componentes.json"
COMPONENTES_URL = (
    f"{BASE_URL}/sigaa/public/departamento/componentes.jsf?id={DEPARTAMENTO_ID}"
)
ID_COMPONENTE_RE = re.compile(r"'id':'(\d+)'")


def extrair_lista_componentes(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    componentes: list[dict[str, str | None]] = []

    for linha in soup.select("tr.linhaImpar, tr.linhaPar"):
        codigo_el = linha.select_one("td.cod")
        nome_el = linha.select_one("td.nome")
        ch_el = linha.select_one("td.ch")
        link_el = linha.select_one("td.ver a[onclick]")

        if codigo_el is None or nome_el is None:
            continue

        onclick = link_el.get("onclick", "") if link_el else ""
        match = ID_COMPONENTE_RE.search(onclick)
        id_sigaa = match.group(1) if match else None

        componentes.append(
            {
                "idSigaa": id_sigaa,
                "codigo": normalizar_texto(codigo_el.get_text()),
                "nome": normalizar_texto(nome_el.get_text()),
                "cargaHoraria": normalizar_texto(ch_el.get_text()) if ch_el else None,
                "ementa": None,
                "urlDetalhe": (
                    url_absoluta(f"/sigaa/link/public/ensino/visualizarComponente/{id_sigaa}")
                    if id_sigaa
                    else None
                ),
            }
        )

    return componentes


def extrair_detalhe_componente(html: str) -> dict[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    detalhes: dict[str, str | None] = {
        "codigo": None,
        "nome": None,
        "cargaHoraria": None,
        "ementa": None,
        "tipo": None,
    }

    for linha in soup.select("table.visualizacao tr"):
        rotulo = linha.find("th")
        valor = linha.find("td")
        if rotulo is None or valor is None:
            continue

        chave = normalizar_texto(rotulo.get_text()).rstrip(":")
        texto = normalizar_texto(valor.get_text(" ", strip=True)) or None

        if chave == "Código":
            detalhes["codigo"] = texto
        elif chave == "Nome":
            detalhes["nome"] = texto
        elif chave.startswith("Carga Horária"):
            detalhes["cargaHoraria"] = texto
        elif chave.startswith("Ementa"):
            detalhes["ementa"] = texto
        elif chave.startswith("Tipo do Componente"):
            detalhes["tipo"] = texto

    return detalhes


def buscar_ementas(
    session,
    componentes: list[dict[str, str | None]],
    *,
    pausa: float,
) -> None:
    buscar_html(session, COMPONENTES_URL, pausa=0)

    ids_unicos = sorted({item["idSigaa"] for item in componentes if item["idSigaa"]})
    cache: dict[str, dict[str, str | None]] = {}

    for indice, id_sigaa in enumerate(ids_unicos):
        if indice > 0 and pausa > 0:
            import time

            time.sleep(pausa)

        url = url_absoluta(f"/sigaa/link/public/ensino/visualizarComponente/{id_sigaa}")
        html = buscar_html(session, url)
        cache[id_sigaa] = extrair_detalhe_componente(html)

    for componente in componentes:
        id_sigaa = componente.get("idSigaa")
        if not id_sigaa or id_sigaa not in cache:
            continue

        detalhe = cache[id_sigaa]
        if detalhe.get("ementa"):
            componente["ementa"] = detalhe["ementa"]
        if detalhe.get("tipo"):
            componente["tipo"] = detalhe["tipo"]


def salvar_json(payload: dict, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(payload, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai componentes curriculares do departamento IESTI no SIGAA."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Arquivo JSON de saída.",
    )
    parser.add_argument(
        "--com-ementa",
        action="store_true",
        help="Busca ementa e tipo de cada componente (mais lento).",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=0.25,
        help="Pausa entre requisições ao buscar ementas (segundos).",
    )
    args = parser.parse_args()

    session = criar_sessao()
    html = buscar_html(session, COMPONENTES_URL)
    componentes = extrair_lista_componentes(html)

    if not componentes:
        raise RuntimeError("Nenhum componente encontrado.")

    if args.com_ementa:
        print(f"Buscando ementas de {len(componentes)} componentes...")
        buscar_ementas(session, componentes, pausa=args.pausa)

    payload = {
        "coletadoEm": datetime.now(timezone.utc).isoformat(),
        "departamentoId": DEPARTAMENTO_ID,
        "fonte": COMPONENTES_URL,
        "total": len(componentes),
        "componentes": componentes,
    }
    salvar_json(payload, args.output)

    com_ementa = sum(1 for item in componentes if item.get("ementa"))
    print(f"Extraídos {len(componentes)} componentes ({com_ementa} com ementa).")
    print(f"Arquivo salvo em: {args.output}")


if __name__ == "__main__":
    main()
