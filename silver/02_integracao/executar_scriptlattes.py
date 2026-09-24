#!/usr/bin/env python3
"""Baixa currículos com scriptLattes e envia os JSONs brutos ao MinIO."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
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

# Persistente entre execuções: o CNPq costuma limitar requisições em massa
# (ERR_CONNECTION_RESET) e o scriptLattes usa esse diretório de cache para não
# baixar de novo um CV já obtido. Um diretório temporário seria apagado a cada
# falha, perdendo o progresso e forçando reiniciar do zero.
CACHE_DIR = ROOT_DIR / ".cache" / "scriptlattes"


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
    """Envia os JSONs já renderizados pelo scriptLattes para o MinIO.

    Tolerante a diretório ausente/vazio (ex.: o scriptLattes falhou antes de
    gerar qualquer saída) para permitir reaproveitar o progresso parcial de
    uma execução anterior que foi interrompida.
    """
    if not diretorio_json.exists():
        return 0

    enviados = 0
    for arquivo in sorted(diretorio_json.glob("*.json")):
        id_lattes = ID_LATTES_RE.search(arquivo.name)
        if not id_lattes:
            print(f"Ignorando arquivo sem ID Lattes no nome: {arquivo.name}")
            continue
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        salvar_json_bronze(f"{prefixo_saida}/{id_lattes.group(1)}.json", dados)
        enviados += 1

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
    parser.add_argument(
        "--limite", type=int, default=0, help="Limita currículos para teste."
    )
    args = parser.parse_args()

    if not SCRIPTLATTES_PYTHON.is_file() or not SCRIPTLATTES_EXECUTAVEL.is_file():
        raise FileNotFoundError(
            "scriptLattes não encontrado ou sem venv em "
            f"{SCRIPTLATTES_DIR}. Esperado: {SCRIPTLATTES_PYTHON}"
        )

    linhas = gerar_lista_lattes(ler_parquet_silver(args.entrada_silver), args.limite)
    if not linhas:
        raise RuntimeError(
            "Nenhum professor com ID Lattes válido foi encontrado na Silver."
        )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    arquivo_lista = CACHE_DIR / "professores_lattes.list"
    diretorio_saida = CACHE_DIR / "saida"
    arquivo_config = CACHE_DIR / "scriptlattes_tcc.config"
    arquivo_lista.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    escrever_config(
        arquivo_config,
        arquivo_lista,
        diretorio_saida,
        CACHE_DIR / "cvs",
    )

    print(f"Baixando {len(linhas)} currículo(s) com scriptLattes...")
    try:
        subprocess.run(
            [
                str(SCRIPTLATTES_PYTHON),
                str(SCRIPTLATTES_EXECUTAVEL),
                str(arquivo_config),
            ],
            cwd=SCRIPTLATTES_DIR,
            check=True,
        )
    except subprocess.CalledProcessError:
        enviados_parciais = enviar_jsons(
            diretorio_saida / "json", args.prefixo_saida.rstrip("/")
        )
        print(
            f"AVISO: o scriptLattes falhou no meio da execução (provável rate limit do "
            f"CNPq). {enviados_parciais} currículo(s) já baixado(s) foram enviados ao "
            f"MinIO antes do erro. O cache foi preservado em {CACHE_DIR} — rode o comando "
            "novamente para continuar de onde parou."
        )
        raise

    enviados = enviar_jsons(diretorio_saida / "json", args.prefixo_saida.rstrip("/"))
    if not enviados:
        raise RuntimeError("Nenhum JSON válido do scriptLattes foi enviado ao MinIO.")

    print(
        f"{enviados} currículo(s) enviado(s) para bronze/{args.prefixo_saida.rstrip('/')}."
    )


if __name__ == "__main__":
    main()
