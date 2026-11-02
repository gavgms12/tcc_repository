"""Utilitários compartilhados pelos scrapers da camada Bronze."""

from __future__ import annotations

import re
import time
import warnings
from typing import Callable

import requests
import urllib3
from bs4 import Tag

from common.lattes import (  # noqa: F401  (reexportados para os scrapers)
    TAMANHO_ID_LATTES,
    extrair_id_lattes,
    id_lattes_valido,
    validar_id_lattes,
)
from common.texto import normalizar_nome, normalizar_texto  # noqa: F401

BASE_URL = "https://sigaa.unifei.edu.br"
DEPARTAMENTO_ID = "127"
SIAPE_RE = re.compile(r"siape=(\d+)", re.IGNORECASE)
USER_AGENT = (
    "Mozilla/5.0 (compatible; TCC-Bronze-Scraper/1.0; +https://unifei.edu.br)"
)


def criar_sessao() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def limpar_nome(nome: str) -> str:
    return re.sub(
        r"\s*\((?:DOUTOR|MESTRE)\)\s*$",
        "",
        nome,
        flags=re.IGNORECASE,
    ).strip()


def extrair_siape(url: str | None) -> str | None:
    if not url:
        return None

    match = SIAPE_RE.search(url)
    return match.group(1) if match else None


def validar_endereco_lattes(url: str | None) -> str | None:
    """Devolve a própria URL do Lattes, só se o id nela contido for válido."""
    if url is None or not id_lattes_valido(extrair_id_lattes(url)):
        return None
    return url


def url_absoluta(caminho: str) -> str:
    if caminho.startswith("http"):
        return caminho
    return f"{BASE_URL}{caminho}"


def buscar_html(
    session: requests.Session | None = None,
    url: str = "",
    *,
    timeout: int = 30,
    pausa: float = 0.0,
    tentativas: int = 3,
    verify: bool = True,
) -> str:
    if pausa > 0:
        time.sleep(pausa)

    sessao = session or criar_sessao()
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            with warnings.catch_warnings():
                # Só silencia o aviso quando a verificação foi desligada de
                # propósito para esta chamada (host com cadeia de certificado
                # incompleta); nunca de forma global.
                if not verify:
                    warnings.simplefilter(
                        "ignore", urllib3.exceptions.InsecureRequestWarning
                    )
                response = sessao.get(url, timeout=timeout, verify=verify)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.RequestException as erro:
            ultimo_erro = erro
            if tentativa < tentativas:
                time.sleep(min(2**tentativa, 8))

    raise ultimo_erro  # type: ignore[misc]


def texto_dd(dd: Tag | None) -> str | None:
    if dd is None:
        return None

    texto = normalizar_texto(dd.get_text(" ", strip=True))
    if not texto or texto.lower() in {
        "não informada",
        "não informado",
        "nao informada",
        "nao informado",
    }:
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
            secoes["enderecoLattes"] = (
                validar_endereco_lattes(link["href"].strip()) if link else None
            )
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
