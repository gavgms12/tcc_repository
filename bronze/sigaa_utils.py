"""Utilitários compartilhados para scraping do SIGAA."""

from __future__ import annotations

import re
import time
from typing import Callable

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://sigaa.unifei.edu.br"
DEPARTAMENTO_ID = "127"
TAMANHO_ID_LATTES = 16
ID_LATTES_NUMERICO = re.compile(r"lattes\.cnpq\.br/(\d+)", re.IGNORECASE)
USER_AGENT = (
    "Mozilla/5.0 (compatible; TCC-Bronze-Scraper/1.0; +https://sigaa.unifei.edu.br)"
)


def criar_sessao() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def limpar_nome(nome: str) -> str:
    return re.sub(
        r"\s*\((?:DOUTOR|MESTRE)\)\s*$",
        "",
        nome,
        flags=re.IGNORECASE,
    ).strip()


def extrair_id_lattes(url: str | None) -> str | None:
    if not url:
        return None
    match = ID_LATTES_NUMERICO.search(url)
    return match.group(1) if match else None


def id_lattes_valido(id_lattes: str | None) -> bool:
    return bool(id_lattes and id_lattes.isdigit() and len(id_lattes) == TAMANHO_ID_LATTES)


def validar_endereco_lattes(url: str | None) -> str | None:
    id_lattes = extrair_id_lattes(url)
    if id_lattes is None or not id_lattes_valido(id_lattes):
        return None
    return url


def url_absoluta(caminho: str) -> str:
    if caminho.startswith("http"):
        return caminho
    return f"{BASE_URL}{caminho}"


def buscar_html(
    session: requests.Session,
    url: str,
    *,
    timeout: int = 30,
    pausa: float = 0.0,
    tentativas: int = 3,
) -> str:
    if pausa > 0:
        time.sleep(pausa)

    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.RequestException as erro:
            ultimo_erro = erro
            if tentativa < tentativas:
                time.sleep(min(2 ** tentativa, 8))

    raise ultimo_erro  # type: ignore[misc]


def texto_dd(dd: Tag | None) -> str | None:
    if dd is None:
        return None

    texto = normalizar_texto(dd.get_text(" ", strip=True))
    if not texto or texto.lower() in {"não informada", "não informado", "nao informada", "nao informado"}:
        return None
    return texto


def extrair_lista_dd(dd: Tag | None) -> list[str]:
    if dd is None:
        return []

    itens: list[str] = []
    for parte in dd.stripped_strings:
        item = re.sub(r"^-\s*", "", parte).strip()
        if item:
            itens.append(item)

    if not itens:
        texto = texto_dd(dd)
        if texto:
            itens = [texto]

    return itens


def extrair_secoes_dl(container: Tag | None) -> dict[str, str | list[str] | None]:
    if container is None:
        return {}

    secoes: dict[str, str | list[str] | None] = {}
    for dl in container.find_all("dl", recursive=False):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if dt is None:
            continue

        chave = normalizar_texto(dt.get_text(" ", strip=True)).rstrip(":")
        chave = re.sub(r"\s*\(.*\)$", "", chave).strip()

        if chave.lower().startswith("áreas de interesse"):
            secoes["areasInteresse"] = extrair_lista_dd(dd)
        elif "formação acadêmica/profissional" in chave.lower():
            secoes["formacaoAcademicaProfissional"] = texto_dd(dd)
        elif chave.lower().startswith("descrição pessoal"):
            secoes["descricaoPessoal"] = texto_dd(dd)
        elif chave.lower().startswith("currículo lattes"):
            link = dd.find("a", href=True) if dd else None
            secoes["enderecoLattes"] = validar_endereco_lattes(link["href"].strip()) if link else None
        elif chave.lower().startswith("endereço profissional"):
            secoes["enderecoProfissional"] = texto_dd(dd)
        elif chave.lower() == "sala":
            secoes["sala"] = texto_dd(dd)
        elif chave.lower().startswith("telefone"):
            secoes["telefone"] = texto_dd(dd)
        elif "eletrônico" in chave.lower() or "eletronico" in chave.lower():
            link = dd.find("a", href=True) if dd else None
            if link and link["href"].startswith("mailto:"):
                secoes["email"] = link["href"].replace("mailto:", "").strip()
            else:
                secoes["email"] = texto_dd(dd)

    return secoes


def iterar_com_pausa(
    itens: list,
    processar: Callable,
    *,
    pausa: float = 0.3,
) -> list:
    resultados = []
    for indice, item in enumerate(itens):
        if indice > 0 and pausa > 0:
            time.sleep(pausa)
        resultados.append(processar(item))
    return resultados
