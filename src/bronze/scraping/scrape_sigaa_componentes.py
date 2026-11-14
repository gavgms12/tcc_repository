#!/usr/bin/env python3
"""Coleta componentes curriculares do departamento no SIGAA."""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[2]
BRONZE_DIR = ROOT_DIR / "bronze"
for caminho in (str(ROOT_DIR), str(BRONZE_DIR)):
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

from bronze.scraping.utils import (
    BASE_URL,
    DEPARTAMENTO_ID,
    buscar_html,
    criar_sessao,
    normalizar_texto,
    url_absoluta,
)
from common.log import configurar_logging
from storage.minio_storage import (
    ler_json_bronze_ultima_versao_ou_none,
    salvar_json_bronze_datado,
)

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = "raw/sigaa/componentes_sigaa.json"
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
                    url_absoluta(
                        f"/sigaa/link/public/ensino/visualizarComponente/{id_sigaa}"
                    )
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
    total = len(ids_unicos)
    rotulo_por_id = {
        item["idSigaa"]: f"{item.get('codigo') or item['idSigaa']} - {item.get('nome') or ''}"
        for item in componentes
        if item.get("idSigaa")
    }
    cache: dict[str, dict[str, str | None]] = {}

    for indice, id_sigaa in enumerate(ids_unicos):
        if indice > 0 and pausa > 0:
            time.sleep(pausa)

        url = url_absoluta(f"/sigaa/link/public/ensino/visualizarComponente/{id_sigaa}")
        html = buscar_html(session, url)
        detalhe = extrair_detalhe_componente(html)
        cache[id_sigaa] = detalhe

        status = "OK" if detalhe.get("ementa") else "sem ementa"
        rotulo = rotulo_por_id.get(id_sigaa, id_sigaa)
        logger.info("[%d/%d] %s -> %s", indice + 1, total, rotulo, status)

    for componente in componentes:
        id_sigaa = componente.get("idSigaa")
        if not id_sigaa or id_sigaa not in cache:
            continue

        detalhe = cache[id_sigaa]
        # Distingue "ainda não buscado" de "buscado e sem ementa na fonte".
        componente["ementaConsultada"] = True
        if detalhe.get("ementa"):
            componente["ementa"] = detalhe["ementa"]
        if detalhe.get("tipo"):
            componente["tipo"] = detalhe["tipo"]


def aplicar_ementas_anteriores(
    componentes: list[dict], anterior: dict | None
) -> int:
    """Reaproveita ementa/tipo já coletados numa execução anterior.

    As ementas quase nunca mudam e buscá-las custa uma requisição por
    componente (~12 min). Só os componentes sem ementa conhecida são buscados
    de novo. Devolve quantos foram preenchidos a partir do histórico.
    """
    if not anterior:
        return 0
    conhecidos = {
        c["idSigaa"]: c
        for c in anterior.get("componentes", [])
        if c.get("ementa") or c.get("ementaConsultada")
    }
    reaproveitados = 0
    for componente in componentes:
        antigo = conhecidos.get(componente.get("idSigaa"))
        if not antigo:
            continue
        componente["ementaConsultada"] = True
        if antigo.get("ementa"):
            componente["ementa"] = antigo["ementa"]
        if antigo.get("tipo"):
            componente["tipo"] = antigo["tipo"]
        reaproveitados += 1
    return reaproveitados


def executar_coleta(
    output: str = DEFAULT_OUTPUT,
    com_ementa: bool = False,
    pausa: float = 0.25,
) -> None:
    """Função utilizada pelo Airflow e pela CLI."""
    session = criar_sessao()
    html = buscar_html(session, COMPONENTES_URL)
    componentes = extrair_lista_componentes(html)

    if not componentes:
        raise RuntimeError("Nenhum componente encontrado.")

    if com_ementa:
        reaproveitados = aplicar_ementas_anteriores(
            componentes, ler_json_bronze_ultima_versao_ou_none(output)
        )
        pendentes = [c for c in componentes if not c.get("ementaConsultada")]
        logger.info(
            "%d ementa(s) reaproveitada(s) da coleta anterior; buscando %d.",
            reaproveitados,
            len(pendentes),
        )
        if pendentes:
            buscar_ementas(session, pendentes, pausa=pausa)

    payload = {
        "coletadoEm": datetime.now(timezone.utc).isoformat(),
        "departamentoId": DEPARTAMENTO_ID,
        "fonte": COMPONENTES_URL,
        "total": len(componentes),
        "componentes": componentes,
    }
    chave = salvar_json_bronze_datado(output, payload)

    com_ementa_total = sum(1 for item in componentes if item.get("ementa"))
    logger.info(
        "Extraídos %d componentes (%d com ementa).", len(componentes), com_ementa_total
    )
    logger.info("Objeto salvo em: bronze/%s", chave)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai componentes curriculares do departamento IESTI no SIGAA."
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Chave do objeto JSON no bucket Bronze.",
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
    configurar_logging()

    executar_coleta(output=args.output, com_ementa=args.com_ementa, pausa=args.pausa)


if __name__ == "__main__":
    main()
