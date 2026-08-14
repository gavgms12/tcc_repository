#!/usr/bin/env python3
"""Pipeline completo da camada Bronze: scraping, merge, lista e scriptLattes."""

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
SCRIPTLATTES_DIR = TCC_ROOT.parent / "scriptLattes"
SCRIPTLATTES_CONFIG = SCRIPTLATTES_DIR / "exemplo" / "teste-02.config"

SIGAA_JSON = BRONZE_DATA / "sigaa" / "professores.json"
SIGAA_COMPONENTES_JSON = BRONZE_DATA / "sigaa" / "componentes.json"
SIGAA_DOCENTES_JSON = BRONZE_DATA / "sigaa" / "docentes.json"
SIGAA_VINCULOS_JSON = BRONZE_DATA / "sigaa" / "vinculos_professor_disciplina.json"
VINCULOS_ICS = BRONZE_DATA / "periodicos" / "trabalhos_vinculados.json"
IESTI_JSON = BRONZE_DATA / "iesti_site" / "professores.json"
PERIODICOS_JSON = BRONZE_DATA / "periodicos" / "trabalhos_ic.json"
MERGED_JSON = BRONZE_DATA / "merged" / "professores.json"
LISTA = BRONZE_DATA / "lista" / "professores.list"
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
    iesti = carregar_json(IESTI_JSON)
    merged = carregar_json(MERGED_JSON)

    lista_linhas = LISTA.read_text(encoding="utf-8").strip().splitlines() if LISTA.exists() else []
    ids_esperados = ids_no_merged(merged)
    ids_json = ids_baixados()
    sem_lattes = [item["nome"] for item in merged if not item.get("idLattes")]
    faltando_json = sorted(ids_esperados - ids_json)
    extras_json = sorted(ids_json - ids_esperados)

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
        f"   Trabalhos IC: {componentes.get('total', 0):>3}",
        f"   Vínculos prof./disc.: {vinculos_sigaa.get('total', 0):>3}",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa o pipeline completo da camada Bronze.")
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Pula scraping e merge; usa arquivos já existentes.",
    )
    parser.add_argument(
        "--skip-lattes",
        action="store_true",
        help="Não executa o scriptLattes (útil para atualizar apenas scraping/merge).",
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
    parser.add_argument(
        "--config",
        type=Path,
        default=SCRIPTLATTES_CONFIG,
        help="Arquivo .config do scriptLattes.",
    )
    args = parser.parse_args()

    python = sys.executable

    if not args.skip_scraping:
        executar_etapa("Scraping SIGAA", [python, "scrape_professores_sigaa.py"])

        comando_componentes = [python, "scrape_sigaa_componentes.py"]
        if args.com_ementa:
            comando_componentes.append("--com-ementa")
        executar_etapa("Componentes SIGAA", comando_componentes)

        comando_docentes = [python, "scrape_sigaa_docente.py"]
        if args.limite_docentes > 0:
            comando_docentes.extend(["--limite", str(args.limite_docentes)])
        executar_etapa("Docentes SIGAA", comando_docentes)

        executar_etapa("Scraping IESTI", [python, "scrape_professores_iesti.py"])
        executar_etapa("Scraping periodicos", [python, "scrape_trabalhos_ic.py"])
        executar_etapa("Merge", [python, "merge_professores.py"])
        executar_etapa(
            "Vincular disciplinas",
            [python, "vincular_disciplinas.py", "--buscar-ementa-vinculadas"],
        )
        executar_etapa(
                    "Vincular trabalhos Iniciação Científica",
                    [python, "vincular_ics.py", "--buscar-ics-vinculadas"],
                )
        executar_etapa("Gerar .list", [python, "lista_lattes/gerar_lista_scriptlattes.py"])

    if not args.skip_lattes:
        venv_python = SCRIPTLATTES_DIR / "venv" / "bin" / "python"
        if not venv_python.exists():
            raise FileNotFoundError(
                f"venv do scriptLattes não encontrada em {venv_python}. "
                "Execute 'make install' no repositório scriptLattes."
            )

        config = args.config.resolve()
        if not config.is_file():
            raise FileNotFoundError(f"Config não encontrado: {config}")

        executar_etapa(
            "scriptLattes",
            [str(venv_python), str(SCRIPTLATTES_DIR / "scriptLattes.py"), str(config)],
            cwd=SCRIPTLATTES_DIR,
        )

    salvar_relatorio(gerar_relatorio())


if __name__ == "__main__":
    main()
