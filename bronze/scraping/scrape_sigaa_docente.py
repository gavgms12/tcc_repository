#!/usr/bin/env python3
"""Coleta dados detalhados de docentes no SIGAA (perfil, disciplinas, produção, pesquisa)."""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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
    buscar_html,
    criar_sessao,
    extrair_secoes_dl,
    normalizar_texto,
    url_absoluta,
)
from common.log import configurar_logging
from storage.minio_storage import ler_json_bronze_ultima_versao, salvar_json_bronze_datado

logger = logging.getLogger(__name__)

# Acima dessa fração de docentes com falha a coleta é considerada inválida e
# nada é gravado; abaixo, o resultado parcial é salvo com as falhas listadas.
MAX_TAXA_FALHA = 0.10
MAX_WORKERS = 4

DEFAULT_PROFESSORES = "raw/sigaa/professores_sigaa.json"
DEFAULT_OUTPUT = "raw/sigaa/docentes_sigaa.json"
ID_COMPONENTE_RE = re.compile(r"visualizarComponente/(\d+)")
CATEGORIA_RE = re.compile(r"\s*\(\d+\)\s*$")


def carregar_professores(chave: str) -> list[dict]:
    return ler_json_bronze_ultima_versao(chave)


def extrair_portal(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    perfil = extrair_secoes_dl(soup.find(id="perfil-docente"))
    contatos = extrair_secoes_dl(soup.find(id="contato"))
    return {"perfil": perfil, "contatos": contatos}


def extrair_disciplinas(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    disciplinas: list[dict[str, str | None]] = []
    periodo_atual: str | None = None

    for linha in soup.select("table tr"):
        celulas = linha.find_all("td")
        if len(celulas) == 1:
            periodo_atual = normalizar_texto(celulas[0].get_text())
            continue

        if len(celulas) < 3:
            continue

        codigo = normalizar_texto(celulas[0].get_text())
        if not codigo or codigo.lower() in {"disciplina", "código"}:
            continue

        link = linha.find("a", href=ID_COMPONENTE_RE)
        id_sigaa = None
        if link and link.get("href"):
            match = ID_COMPONENTE_RE.search(link["href"])
            id_sigaa = match.group(1) if match else None

        disciplinas.append(
            {
                "periodo": periodo_atual,
                "codigo": codigo,
                "nome": normalizar_texto(celulas[1].get_text()),
                "cargaHoraria": normalizar_texto(celulas[2].get_text()),
                "horario": (
                    normalizar_texto(celulas[3].get_text())
                    if len(celulas) > 3
                    else None
                ),
                "idSigaa": id_sigaa,
                "urlComponente": (
                    url_absoluta(link["href"]) if link and link.get("href") else None
                ),
            }
        )

    return disciplinas


def extrair_producao(html: str) -> list[dict[str, str | list[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    center = soup.find(id="center") or soup
    categorias: list[dict[str, str | list[str]]] = []

    for titulo in center.find_all("h2"):
        categoria = CATEGORIA_RE.sub("", titulo.get_text(strip=True)).strip()
        if not categoria:
            continue

        lista = titulo.find_next_sibling("ul")
        if lista is None:
            continue

        itens = [
            normalizar_texto(item.get_text(" ", strip=True))
            for item in lista.find_all("li", recursive=False)
            if normalizar_texto(item.get_text(" ", strip=True))
        ]
        if itens:
            categorias.append({"categoria": categoria, "itens": itens})

    return categorias


def extrair_pesquisa(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    projetos: list[dict[str, str | None]] = []
    ano_atual: str | None = None

    for linha in soup.select("table tr"):
        celulas = linha.find_all("td")
        if len(celulas) == 1:
            ano_atual = normalizar_texto(celulas[0].get_text())
            continue

        if len(celulas) < 2:
            continue

        codigo = normalizar_texto(celulas[0].get_text())
        if not codigo or codigo.lower() in {"projeto de pesquisa", "código"}:
            continue

        projetos.append(
            {
                "ano": ano_atual,
                "codigo": codigo,
                "titulo": normalizar_texto(celulas[1].get_text()),
                "areaConhecimento": (
                    normalizar_texto(celulas[2].get_text())
                    if len(celulas) > 2
                    else None
                ),
            }
        )

    return projetos


def coletar_docente(session, siape: str, nome: str) -> dict:
    base = f"{BASE_URL}/sigaa/public/docente"
    urls = {
        "portal": f"{base}/portal.jsf?siape={siape}",
        "disciplinas": f"{base}/disciplinas.jsf?siape={siape}",
        "producao": f"{base}/producao.jsf?siape={siape}",
        "pesquisa": f"{base}/pesquisa.jsf?siape={siape}",
    }

    html_portal = buscar_html(session, urls["portal"])
    html_disciplinas = buscar_html(session, urls["disciplinas"])
    html_producao = buscar_html(session, urls["producao"])
    html_pesquisa = buscar_html(session, urls["pesquisa"])

    portal = extrair_portal(html_portal)
    disciplinas = extrair_disciplinas(html_disciplinas)

    return {
        "siape": siape,
        "nome": nome,
        "urlsSigaa": urls,
        "perfil": portal["perfil"],
        "contatos": portal["contatos"],
        "disciplinasMinistradas": disciplinas,
        "producaoIntelectual": extrair_producao(html_producao),
        "projetosPesquisa": extrair_pesquisa(html_pesquisa),
    }


def executar_coleta(
    professores: str = DEFAULT_PROFESSORES,
    output: str = DEFAULT_OUTPUT,
    limite: int = 0,
    pausa: float = 0.3,
) -> None:
    """Função utilizada pelo Airflow e pela CLI."""
    lista_professores = carregar_professores(professores)
    com_siape = [prof for prof in lista_professores if prof.get("siape")]
    if limite > 0:
        com_siape = com_siape[:limite]

    if not com_siape:
        raise RuntimeError("Nenhum professor com siape encontrado.")

    total = len(com_siape)

    def tarefa(item: tuple[int, dict]) -> tuple[dict | None, dict | None]:
        indice, professor = item
        siape = professor["siape"]
        nome = professor.get("nome", "")
        if pausa > 0:
            time.sleep(pausa)
        logger.info("[%d/%d] Coletando %s (siape=%s)...", indice + 1, total, nome, siape)
        try:
            # Uma sessão por tarefa: requests.Session não é thread-safe.
            return coletar_docente(criar_sessao(), siape, nome), None
        except Exception as erro:  # um docente com falha não derruba a coleta
            logger.error("Falha ao coletar %s (siape=%s): %s", nome, siape, erro)
            return None, {"siape": siape, "nome": nome, "erro": str(erro)}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        resultados = list(pool.map(tarefa, enumerate(com_siape)))

    docentes = [ok for ok, _ in resultados if ok]
    falhas = [erro for _, erro in resultados if erro]

    if len(falhas) / total > MAX_TAXA_FALHA:
        raise RuntimeError(
            f"{len(falhas)} de {total} docentes falharam (limite "
            f"{MAX_TAXA_FALHA:.0%}); nada foi gravado. Falhas: "
            + ", ".join(f["siape"] for f in falhas)
        )

    payload = {
        "coletadoEm": datetime.now(timezone.utc).isoformat(),
        "total": len(docentes),
        "falhas": falhas,
        "docentes": docentes,
    }
    chave = salvar_json_bronze_datado(output, payload)

    total_disciplinas = sum(len(doc["disciplinasMinistradas"]) for doc in docentes)
    logger.info(
        "Coletados %d docentes (%d registros de disciplina, %d falha(s)).",
        len(docentes),
        total_disciplinas,
        len(falhas),
    )
    logger.info("Objeto salvo em: bronze/%s", chave)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai perfil, disciplinas, produção e pesquisa dos docentes no SIGAA."
    )
    parser.add_argument(
        "--professores",
        default=DEFAULT_PROFESSORES,
        help="Chave do JSON de professores no bucket Bronze.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Chave do objeto JSON no bucket Bronze.",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=0,
        help="Limita quantidade de docentes (0 = todos).",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=0.3,
        help="Pausa entre docentes (segundos).",
    )
    args = parser.parse_args()
    configurar_logging()

    executar_coleta(
        professores=args.professores,
        output=args.output,
        limite=args.limite,
        pausa=args.pausa,
    )


if __name__ == "__main__":
    main()
