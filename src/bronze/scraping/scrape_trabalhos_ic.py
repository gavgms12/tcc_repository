"""Web scraping dos trabalhos de Iniciação Científica dos docentes do site do IESTI (camada Bronze)."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bronze.scraping.utils import buscar_html, criar_sessao, normalizar_texto
from common.config import ANO_MINIMO
from common.log import configurar_logging
from storage.minio_storage import (
    ler_json_bronze_ultima_versao_ou_none,
    salvar_json_bronze_datado,
)

logger = logging.getLogger(__name__)

SECOES_ALVO = {
    "Ciência da Computação e Engenharia da Computação",
    "Engenharia Elétrica, Eletrônica, Controle e Automação",
}

DEFAULT_URL = "https://periodicos.unifei.edu.br/index.php/rtic/issue/archive"
DEFAULT_OUTPUT = "raw/periodicos/trabalhos_ic_periodicos.json"


def get_urls_edicoes_ics(session, *, verify_ssl: bool = False) -> list[dict]:
    html = buscar_html(session, DEFAULT_URL, verify=verify_ssl)
    soup = BeautifulSoup(html, "html.parser")

    urls: list[dict] = []
    for edicao in soup.find_all("h2"):
        nome_tag = edicao.find("a")
        ano_tag = edicao.find("div", class_="series")
        if not (nome_tag and ano_tag):
            continue

        ano_numero = int(ano_tag.get_text().strip())
        # As edições vêm da mais recente para a mais antiga; parar aqui evita
        # baixar centenas de páginas fora da janela de relevância.
        if ano_numero < ANO_MINIMO:
            break
        urls.append({"url": str(nome_tag["href"]), "ano": ano_numero})

    return urls


def indexar_trabalhos_anteriores(anterior: list[dict] | None) -> dict[str, dict]:
    """Indexa a coleta anterior pela URL do artigo.

    Um artigo publicado não muda; reaproveitar resumo e palavras-chave evita
    uma requisição por trabalho (a etapa mais lenta da Bronze). Registros de
    coletas antigas, sem `url`, simplesmente não entram no índice.
    """
    return {
        t["url"]: t
        for t in anterior or []
        if t.get("url") and t["url"] != "Não informado"
    }


def extrair_trabalhos(
    session,
    urls: list[dict],
    *,
    verify_ssl: bool = False,
    anteriores: dict[str, dict] | None = None,
) -> list[dict]:
    anteriores = anteriores or {}
    trabalhos = []
    reaproveitados = buscados = 0

    for url in urls:
        html = buscar_html(session, url["url"], verify=verify_ssl)
        soup = BeautifulSoup(html, "html.parser")

        # Obter informações de cada um dos trabalhos [titulo, autores e url] da página de IC
        for secao in soup.find_all("div", class_="section"):
            h2 = secao.find("h2")
            if not (h2 and normalizar_texto(h2.get_text()) in SECOES_ALVO):
                continue

            for tag in secao.find_all("div", class_="obj_article_summary"):
                titulo_tag = tag.find("a")
                autores_tag = tag.find("div", class_="authors")
                palavras_chaves: list[str] = []

                if titulo_tag and autores_tag:
                    trabalho_autores = re.sub(
                        r"[\s\x00-\x1F\x7F]+", " ", autores_tag.get_text()
                    ).strip()
                    trabalho_titulo = re.sub(
                        r"[\s\x00-\x1F\x7F]+", " ", titulo_tag.get_text()
                    ).strip()
                    trabalho_url = str(titulo_tag["href"])
                else:
                    trabalho_titulo = "Não informado"
                    trabalho_url = "Não informado"
                    trabalho_autores = "Não informado"

                anterior = anteriores.get(trabalho_url)
                if anterior:
                    resumo = anterior.get("resumo")
                    palavras_chaves = list(anterior.get("palavrasChaves") or [])
                    reaproveitados += 1
                else:
                    # Ir até a página do trabalho e obter as palavras-chaves associadas
                    html_trabalho = buscar_html(session, trabalho_url, verify=verify_ssl)
                    soup_trabalho = BeautifulSoup(html_trabalho, "html.parser")
                    for palavra_chave in soup_trabalho.find_all(
                        "meta", attrs={"name": "citation_keywords"}
                    ):
                        palavras_chaves.append(palavra_chave["content"])

                    secao_resumo = soup_trabalho.find("section", class_="item abstract")
                    resumo = None
                    if secao_resumo:
                        paragrafo = secao_resumo.find("p")
                        if paragrafo:
                            resumo = normalizar_texto(paragrafo.get_text(separator=" "))
                    buscados += 1

                trabalhos.append(
                    {
                        "titulo": trabalho_titulo,
                        "url": trabalho_url,
                        "autores": trabalho_autores,
                        "resumo": resumo,
                        "palavrasChaves": palavras_chaves,
                        "ano": url["ano"],
                    }
                )

    logger.info(
        "%d trabalho(s) reaproveitado(s) da coleta anterior; %d buscado(s).",
        reaproveitados,
        buscados,
    )
    return trabalhos


def executar_coleta(
    url: str = DEFAULT_URL,
    output: str = DEFAULT_OUTPUT,
    verify_ssl: bool = False,
) -> None:
    """Função utilizada pelo Airflow e pela CLI."""
    session = criar_sessao()
    urls = get_urls_edicoes_ics(session, verify_ssl=verify_ssl)
    anteriores = indexar_trabalhos_anteriores(ler_json_bronze_ultima_versao_ou_none(output))
    trabalhos = extrair_trabalhos(
        session, urls, verify_ssl=verify_ssl, anteriores=anteriores
    )

    if not trabalhos:
        raise RuntimeError("Nenhum trabalho encontrado. Verifique a estrutura da página.")

    chave = salvar_json_bronze_datado(output, trabalhos)

    logger.info("Extraídos %d trabalhos de IC.", len(trabalhos))
    logger.info("Objeto salvo em: bronze/%s", chave)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai nome do titulo e palavras-chaves dos trabalhos de IC."
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL, help="URL da página dos eventos de IC."
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Chave do objeto JSON no bucket Bronze.",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Valida o certificado SSL (desabilitado por padrão: certificado do site UNIFEI).",
    )
    args = parser.parse_args()
    configurar_logging()

    executar_coleta(url=args.url, output=args.output, verify_ssl=args.verify_ssl)


if __name__ == "__main__":
    main()
