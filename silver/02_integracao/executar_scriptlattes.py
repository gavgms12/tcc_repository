#!/usr/bin/env python3
"""Baixa currículos com scriptLattes e envia os JSONs brutos ao MinIO."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bronze.minio_storage import ler_parquet_silver, salvar_json_bronze

SCRIPTLATTES_DIR = ROOT_DIR.parent / "scriptLattes"
SCRIPTLATTES_PYTHON = SCRIPTLATTES_DIR / "venv" / "bin" / "python"
SCRIPTLATTES_EXECUTAVEL = SCRIPTLATTES_DIR / "scriptLattes.py"
DEFAULT_ENTRADA_SILVER = "professores_unificados.parquet"
DEFAULT_PREFIXO_SAIDA = "raw/lattes/json"
ID_LATTES_RE = re.compile(r"(\d{16})(?:\.json)?$")


def gerar_lista_lattes(professores: list[dict], limite: int = 0) -> list[str]:
    """Converte os professores unificados no formato aceito pelo scriptLattes."""
    linhas: list[str] = []
    for professor in professores:
        id_lattes = str(professor.get("idLattes") or "").strip()
        nome = str(professor.get("nome") or "").strip()
        if id_lattes.isdigit() and len(id_lattes) == 16 and nome:
            linhas.append(f"{id_lattes}, {nome}")

    if limite > 0:
        linhas = linhas[:limite]
    return linhas


def escrever_config(caminho: Path, entrada: Path, saida: Path, cache: Path) -> None:
    """Cria uma configuração isolada; não modifica exemplos do scriptLattes."""
    caminho.write_text(
        "\n".join(
            [
                "global-nome_do_grupo = IESTI-UNIFEI",
                f"global-arquivo_de_entrada = {entrada}",
                f"global-diretorio_de_saida = {saida}",
                f"global-diretorio_de_armazenamento_de_cvs = {cache}",
                "global-email_do_admin = admin@email.com",
                "global-idioma = PT",
                "global-itens_por_pagina = 5000",
                "",
            ]
        ),
        encoding="utf-8",
    )


def enviar_jsons(diretorio_json: Path, prefixo_saida: str) -> int:
    arquivos = sorted(diretorio_json.glob("*.json"))
    if not arquivos:
        raise FileNotFoundError(f"O scriptLattes não gerou JSONs em {diretorio_json}.")

    enviados = 0
    for arquivo in arquivos:
        id_lattes = ID_LATTES_RE.search(arquivo.name)
        if not id_lattes:
            print(f"Ignorando arquivo sem ID Lattes no nome: {arquivo.name}")
            continue
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        salvar_json_bronze(f"{prefixo_saida}/{id_lattes.group(1)}.json", dados)
        enviados += 1

    if not enviados:
        raise RuntimeError("Nenhum JSON válido do scriptLattes foi enviado ao MinIO.")
    return enviados


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa scriptLattes e envia currículos brutos para a Bronze no MinIO."
    )
    parser.add_argument(
        "--entrada-silver",
        default=DEFAULT_ENTRADA_SILVER,
        help="Chave Parquet do cadastro unificado no bucket Silver.",
    )
    parser.add_argument(
        "--prefixo-saida",
        default=DEFAULT_PREFIXO_SAIDA,
        help="Prefixo dos JSONs de currículo no bucket Bronze.",
    )
    parser.add_argument("--limite", type=int, default=0, help="Limita currículos para teste.")
    args = parser.parse_args()

    if not SCRIPTLATTES_PYTHON.is_file() or not SCRIPTLATTES_EXECUTAVEL.is_file():
        raise FileNotFoundError(
            "scriptLattes não encontrado ou sem venv em "
            f"{SCRIPTLATTES_DIR}. Esperado: {SCRIPTLATTES_PYTHON}"
        )

    linhas = gerar_lista_lattes(ler_parquet_silver(args.entrada_silver), args.limite)
    if not linhas:
        raise RuntimeError("Nenhum professor com ID Lattes válido foi encontrado na Silver.")

    with tempfile.TemporaryDirectory(prefix="tcc_scriptlattes_") as temporario:
        diretorio_temporario = Path(temporario)
        arquivo_lista = diretorio_temporario / "professores_lattes.list"
        diretorio_saida = diretorio_temporario / "saida"
        arquivo_config = diretorio_temporario / "scriptlattes_tcc.config"
        arquivo_lista.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        escrever_config(
            arquivo_config,
            arquivo_lista,
            diretorio_saida,
            diretorio_temporario / "cache",
        )

        print(f"Baixando {len(linhas)} currículo(s) com scriptLattes...")
        subprocess.run(
            [str(SCRIPTLATTES_PYTHON), str(SCRIPTLATTES_EXECUTAVEL), str(arquivo_config)],
            cwd=SCRIPTLATTES_DIR,
            check=True,
        )
        enviados = enviar_jsons(diretorio_saida / "json", args.prefixo_saida.rstrip("/"))

    print(f"{enviados} currículo(s) enviado(s) para bronze/{args.prefixo_saida.rstrip('/')}.")


if __name__ == "__main__":
    main()
