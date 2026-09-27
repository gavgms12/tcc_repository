"""Web scraping dos trabalhos de Iniciação Científica dos docentes do site do IESTI (camada Bronze)."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bronze.scraping.utils import buscar_html, criar_sessao, normalizar_texto
from storage.minio_storage import salvar_json_bronze

ANO_LIMITE = datetime.now().year - 10

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
        if ano_numero < ANO_LIMITE:
            break
        urls.append({"url": str(nome_tag["href"]), "ano": ano_numero})

    return urls


def extrair_trabalhos(session, urls: list[dict], *, verify_ssl: bool = False) -> list[dict]:
    trabalhos = []

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

                trabalhos.append(
                    {
                        "titulo": trabalho_titulo,
                        "autores": trabalho_autores,
                        "resumo": resumo,
                        "palavrasChaves": palavras_chaves,
                        "ano": url["ano"],
                    }
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
    trabalhos = extrair_trabalhos(session, urls, verify_ssl=verify_ssl)

    if not trabalhos:
        raise RuntimeError("Nenhum trabalho encontrado. Verifique a estrutura da página.")

    salvar_json_bronze(output, trabalhos)

    print(f"Objeto salvo em: bronze/{output}")
    print(f"Coletado em: {datetime.now(timezone.utc).isoformat()}")


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

    executar_coleta(url=args.url, output=args.output, verify_ssl=args.verify_ssl)


if __name__ == "__main__":
    main()
