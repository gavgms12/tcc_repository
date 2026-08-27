#!/usr/bin/env python3
"""Pipeline da camada Bronze: coleta os dados brutos das fontes públicas."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BRONZE_DIR = Path(__file__).resolve().parent
TCC_ROOT = BRONZE_DIR.parent
BRONZE_DATA = TCC_ROOT / "data" / "bronze"
SIGAA_JSON = BRONZE_DATA / "raw" / "sigaa" / "professores_sigaa.json"
SIGAA_COMPONENTES_JSON = BRONZE_DATA / "raw" / "sigaa" / "componentes_sigaa.json"
SIGAA_DOCENTES_JSON = BRONZE_DATA / "raw" / "sigaa" / "docentes_sigaa.json"
SIGAA_VINCULOS_JSON = BRONZE_DATA / "raw" / "sigaa" / "vinculos_professor_disciplina.json"
VINCULOS_ICS = BRONZE_DATA / "raw" / "periodicos" / "trabalhos_vinculados.json"
IESTI_JSON = BRONZE_DATA / "raw" / "iesti_site" / "professores_iesti_site.json"
PERIODICOS_JSON = BRONZE_DATA / "raw" / "periodicos" / "trabalhos_ic_periodicos.json"
MERGED_JSON = BRONZE_DATA / "merged" / "professores_sigaa_iesti_merged.json"
LISTA = BRONZE_DATA / "lista" / "professores_lattes.list"
LATTES_JSON_DIR = BRONZE_DATA / "lattes" / "json"
RELATORIO = BRONZE_DATA / "relatorio_qualidade.txt"


def executar_etapa(nome: str, comando: list[str], cwd: Path | None = None) -> None:
    print(f"\n=== {nome} ===")
    resultado = subprocess.run(comando, cwd=cwd or BRONZE_DIR, check=False)
    if resultado.returncode != 0:
        raise RuntimeError(f"Etapa '{nome}' falhou com código {resultado.returncode}.")


def contar_com_lattes_sigaa(dados: list[dict]) -> int:
    return sum(1 for item in dados if item.get("enderecoLattes"))


def contar_com_siape(dados: list[dict]) -> int:
    return sum(1 for item in dados if item.get("siape"))


def carregar_payload_sigaa(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def contar_com_lattes_iesti(dados: list[dict]) -> int:
    return sum(1 for item in dados if item.get("idLattes"))


def carregar_json(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def ids_no_merged(dados: list[dict]) -> set[str]:
    return {item["idLattes"] for item in dados if item.get("idLattes")}


def ids_baixados() -> set[str]:
    if not LATTES_JSON_DIR.exists():
        return set()

    ids: set[str] = set()
    for arquivo in LATTES_JSON_DIR.glob("*.json"):
        partes = arquivo.stem.split("_")
        if partes:
            ids.add(partes[-1])
    return ids


def gerar_relatorio() -> str:
    agora = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    sigaa = carregar_json(SIGAA_JSON)
    componentes = carregar_payload_sigaa(SIGAA_COMPONENTES_JSON)
    docentes_sigaa = carregar_payload_sigaa(SIGAA_DOCENTES_JSON)
    vinculos_sigaa = carregar_payload_sigaa(SIGAA_VINCULOS_JSON)
    vinculos_ics = carregar_payload_sigaa(VINCULOS_ICS)
    periodicos = carregar_payload_sigaa(PERIODICOS_JSON)
    iesti = carregar_json(IESTI_JSON)
    merged = carregar_json(MERGED_JSON)

    lista_linhas = LISTA.read_text(encoding="utf-8").strip().splitlines() if LISTA.exists() else []
    ids_esperados = ids_no_merged(merged)
    ids_json = ids_baixados()
    sem_lattes = [item["nome"] for item in merged if not item.get("idLattes")]
    faltando_json = sorted(ids_esperados - ids_json)
    extras_json = sorted(ids_json - ids_esperados)

    total_trabalhos_ic = (
        len(periodicos) if isinstance(periodicos, list) else periodicos.get("total", 0)
    )
    if isinstance(vinculos_ics, list):
        total_vinculos_ics = sum(
            1 for item in vinculos_ics if item.get("professoresVinculados")
        )
    elif isinstance(vinculos_ics, dict):
        vinculos_lista = vinculos_ics.get("vinculos", vinculos_ics.get("trabalhos", []))
        total_vinculos_ics = sum(
            1 for item in vinculos_lista if item.get("professoresVinculados")
        )
    else:
        total_vinculos_ics = 0

    linhas = [
        "RELATÓRIO DE QUALIDADE — CAMADA BRONZE",
        "=" * 50,
        f"Gerado em: {agora}",
        "",
        "1. FONTES BRUTAS",
        f"   SIGAA:      {len(sigaa):>3} professores | {contar_com_lattes_sigaa(sigaa):>3} com link Lattes",
        f"               {contar_com_siape(sigaa):>3} com siape",
        f"   IESTI site: {len(iesti):>3} professores | {contar_com_lattes_iesti(iesti):>3} com idLattes",
        f"   Componentes SIGAA: {componentes.get('total', 0):>3}",
        f"   Docentes SIGAA:    {docentes_sigaa.get('total', 0):>3}",
        f"   Trabalhos IC: {total_trabalhos_ic:>3}",
        f"   Vínculos prof./disc.: {vinculos_sigaa.get('total', 0):>3}",
        f"   Vínculos prof./IC:    {total_vinculos_ics:>3}",
        "",
        "2. CADASTRO MESCLADO",
        f"   Total:      {len(merged):>3} professores",
        f"   Com idLattes: {len(ids_esperados):>3}",
        f"   Sem idLattes: {len(sem_lattes):>3}",
    ]

    if sem_lattes:
        linhas.append("   Professores sem Lattes:")
        for nome in sem_lattes:
            linhas.append(f"     - {nome}")

    linhas.extend(
        [
            "",
            "3. LISTA PARA SCRIPTLATTES",
            f"   Linhas no .list: {len(lista_linhas)}",
            f"   Arquivo: {LISTA}",
            "",
            "4. CURRÍCULOS BAIXADOS (JSON)",
            f"   Esperados: {len(ids_esperados)}",
            f"   Baixados:  {len(ids_json)}",
            f"   Diretório: {LATTES_JSON_DIR}",
        ]
    )

    if faltando_json:
        linhas.append("   IDs sem JSON:")
        for id_lattes in faltando_json:
            linhas.append(f"     - {id_lattes}")

    if extras_json:
        linhas.append("   JSONs extras (não presentes no merge):")
        for id_lattes in extras_json:
            linhas.append(f"     - {id_lattes}")

    cobertura = (len(ids_json) / len(ids_esperados) * 100) if ids_esperados else 0.0
    linhas.extend(
        [
            "",
            "5. RESUMO",
            f"   Cobertura Lattes: {cobertura:.1f}%",
            f"   Status: {'OK' if not sem_lattes and not faltando_json else 'ATENÇÃO — revisar lacunas acima'}",
        ]
    )

    return "\n".join(linhas) + "\n"


def salvar_relatorio(conteudo: str) -> None:
    RELATORIO.write_text(conteudo, encoding="utf-8")
    print(conteudo)
    print(f"Relatório salvo em: {RELATORIO}")


def verificar_dependencias() -> None:
    faltando: list[str] = []
    try:
        import requests  # noqa: F401
    except ImportError:
        faltando.append("requests")
    try:
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError:
        faltando.append("beautifulsoup4")
    if faltando:
        print(
            "Dependências ausentes: "
            + ", ".join(faltando)
            + "\n\nAtive a venv do projeto (tcc_code/venv) e instale:\n"
            "  cd tcc_code && source venv/bin/activate\n"
            "  pip install -r bronze/requirements.txt\n\n"
            "Não use a venv do scriptLattes para os scripts Bronze.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    verificar_dependencias()
    parser = argparse.ArgumentParser(description="Executa a coleta da camada Bronze.")
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Pula a coleta e usa os arquivos brutos já existentes.",
    )
    parser.add_argument(
        "--com-ementa",
        action="store_true",
        help="Busca ementa de todos os componentes curriculares (mais lento).",
    )
    parser.add_argument(
        "--limite-docentes",
        type=int,
        default=0,
        help="Limita coleta detalhada de docentes no SIGAA (0 = todos).",
    )
    args = parser.parse_args()

    python = sys.executable

    if not args.skip_scraping:
        executar_etapa("Scraping SIGAA", [python, "scraping/scrape_professores_sigaa.py"])

        comando_componentes = [python, "scraping/scrape_sigaa_componentes.py"]
        if args.com_ementa:
            comando_componentes.append("--com-ementa")
        executar_etapa("Componentes SIGAA", comando_componentes)

        comando_docentes = [python, "scraping/scrape_sigaa_docente.py"]
        if args.limite_docentes > 0:
            comando_docentes.extend(["--limite", str(args.limite_docentes)])
        executar_etapa("Docentes SIGAA", comando_docentes)

        executar_etapa("Scraping IESTI", [python, "scraping/scrape_professores_iesti.py"])
        executar_etapa("Scraping periodicos", [python, "scraping/scrape_trabalhos_ic.py"])

    if MERGED_JSON.exists():
        salvar_relatorio(gerar_relatorio())
    else:
        print("\nRelatório não gerado: o merge é executado na camada Silver.")


if __name__ == "__main__":
    main()
