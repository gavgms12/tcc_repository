"""Web scraping dos trabalhos de Iniciação Científica dos docentes do site do IESTI (camada Bronze)."""
from __future__ import annotations

import argparse
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timezone
import json
import unicodedata
from pathlib import Path
import urllib3

ano_limite = datetime.now().year - 4

secoes_alvo = {
    'Ciência da Computação e Engenharia da Computação',
    'Engenharia Elétrica, Eletrônica, Controle e Automação',
}

DEFAULT_URL = "https://periodicos.unifei.edu.br/index.php/rtic/issue/archive"
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT_DIR / "data" / "bronze" / "periodicos" / "trabalhos_ic.json"

urls = []

def salvar_json(dados: list[dict[str, str | None]], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
        
def normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_nome(nome: str) -> str:
    nome = normalizar_texto(nome)
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(char for char in nome if not unicodedata.combining(char))
    return nome.upper()

def buscar_html(url: str, timeout: int = 30, verify_ssl: bool = True) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        verify=verify_ssl,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; TCC-Bronze-Scraper/1.0; "
                "+https://iesti.unifei.edu.br)"
            )
        },
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text

def get_urls_edicoes_ICS():
    urls = []
    url_arquivos = "https://periodicos.unifei.edu.br/index.php/rtic/issue/archive"
    # adicionar lógica de pegar só até um determinado ano de IC 
    html = buscar_html(url_arquivos)
    soup = BeautifulSoup(html, 'html.parser')

    edicoes_tags = soup.find_all('h2')
    for edicoes in edicoes_tags:
        nome_tag = edicoes.find('a')
        ano_tag = edicoes.find('div', class_ ='series')
        if nome_tag and ano_tag:
            url_tag = str(nome_tag['href'])
            ano = ano_tag.get_text().strip()
            ano_numero = int(ano)
        
            if ano_numero < ano_limite:
                break
            else:
                urls.append(url_tag)        
    return urls
            # ---------------------

urls = get_urls_edicoes_ICS()

def extrair_trabalhos(urls: list[str]):
    trabalhos = []

    for url in urls:
            html = buscar_html(url)
            soup = BeautifulSoup(html, "html.parser")
                
            # Obter informações de cada um dos trabalhos [titulo, autores e url] da página de IC
            tag_secoes = soup.find_all('div', class_ = 'section')
            for secao in tag_secoes:
                h2 = secao.find('h2')
                if h2 and (normalizar_texto(h2.get_text())) in secoes_alvo:
                    trabalhos_tags = secao.find_all('div', class_ ='obj_article_summary')
                    for tag in trabalhos_tags:
                        trabalho_tag = tag.find('h3', class_ ='title')
                        titulo_tag = tag.find('a')
                        autores_tag = tag.find('div', class_ = 'authors')
                        palavras_chaves = []
                            
                        if titulo_tag and autores_tag:
                            # verificar se o autor tem algum professor que queremos consultar -> dar match em pelo menos três nomes? abreviação l.
                            trabalho_autores = re.sub(r'[\s\x00-\x1F\x7F]+', ' ', autores_tag.get_text()).strip()
                            trabalho_titulo = re.sub(r'[\s\x00-\x1F\x7F]+', ' ', titulo_tag.get_text()).strip()
                            trabalho_url = str(titulo_tag['href'])

                        else:
                            trabalho_titulo = "Não informado"
                            trabalho_url = "Não informado"
                            trabalho_autores = "Não informado"
                            # Ir até a página do trabalho e obter as palavras-chaves associadas
                            
                        html_trabalho = buscar_html(trabalho_url)    
                        soup_trabalho = BeautifulSoup(html_trabalho, "html.parser")
                        palavras_chaves_tag = soup_trabalho.find_all('meta',  attrs={"name": "citation_keywords"})
                        for palavra_chave in palavras_chaves_tag:
                            palavras_chaves.append(palavra_chave["content"])
                            
                        trabalhos.append(   
                            {
                                "Titulo" : trabalho_titulo,
                                "Autores" : trabalho_autores,
                                #"URL" : trabalho_url,
                                "Palavras-chave" : palavras_chaves
                                #"Ano" : url['Ano']
                            }
                        )                
    return trabalhos

def main() -> None:
    parser = argparse.ArgumentParser(
            description="Extrai nome do titulo e palavras-chaves dos trabalhos de IC."
        )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL da página dos eventos de IC.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Arquivo JSON de saída.")
    parser.add_argument("--verify-ssl", action="store_true", help="Valida o certificado SSL...")
    
    args = parser.parse_args()
    
    if not args.verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    urls = get_urls_edicoes_ICS()
    print(urls)
    trabalhos = extrair_trabalhos(urls)
    
    if not trabalhos:
        raise RuntimeError("Nenhum trabalho encontrado. Verifique a estrutura da página.")
    
    salvar_json(trabalhos, args.output)
    
    print(f"Arquivo salvo em: {args.output}")
    print(f"Coletado em: {datetime.now(timezone.utc).isoformat()}")
    
if __name__ == "__main__":
    main()