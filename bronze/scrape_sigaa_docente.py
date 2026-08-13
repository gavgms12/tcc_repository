#!/usr/bin/env python3
"""Coleta dados detalhados de docentes no SIGAA (perfil, disciplinas, produção, pesquisa)."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from sigaa_utils import (
    BASE_URL,
    buscar_html,
    criar_sessao,
    extrair_secoes_dl,
    normalizar_texto,
    url_absoluta,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROFESSORES = ROOT_DIR / "data" / "bronze" / "sigaa" / "professores.json"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "bronze" / "sigaa" / "docentes.json"
ID_COMPONENTE_RE = re.compile(r"visualizarComponente/(\d+)")
CATEGORIA_RE = re.compile(r"\s*\(\d+\)\s*$")


def carregar_professores(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


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
                    normalizar_texto(celulas[3].get_text()) if len(celulas) > 3 else None
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
                    normalizar_texto(celulas[2].get_text()) if len(celulas) > 2 else None
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


def salvar_json(payload: dict, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(payload, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai perfil, disciplinas, produção e pesquisa dos docentes no SIGAA."
    )
    parser.add_argument(
        "--professores",
        type=Path,
        default=DEFAULT_PROFESSORES,
        help="JSON com lista de professores (saída do scrape_professores_sigaa).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Arquivo JSON de saída.",
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

    professores = carregar_professores(args.professores)
    com_siape = [prof for prof in professores if prof.get("siape")]
    if args.limite > 0:
        com_siape = com_siape[: args.limite]

    if not com_siape:
        raise RuntimeError("Nenhum professor com siape encontrado.")

    session = criar_sessao()
    docentes: list[dict] = []

    for indice, professor in enumerate(com_siape):
        if indice > 0 and args.pausa > 0:
            import time

            time.sleep(args.pausa)

        siape = professor["siape"]
        nome = professor.get("nome", "")
        print(f"[{indice + 1}/{len(com_siape)}] Coletando {nome} (siape={siape})...")
        docentes.append(coletar_docente(session, siape, nome))

    payload = {
        "coletadoEm": datetime.now(timezone.utc).isoformat(),
        "total": len(docentes),
        "docentes": docentes,
    }
    salvar_json(payload, args.output)

    total_disciplinas = sum(len(doc["disciplinasMinistradas"]) for doc in docentes)
    print(f"\nColetados {len(docentes)} docentes ({total_disciplinas} registros de disciplina).")
    print(f"Arquivo salvo em: {args.output}")


if __name__ == "__main__":
    main()
