#!/usr/bin/env python3
"""Baixa currículos com scriptLattes e envia os JSONs brutos ao MinIO."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.log import configurar_logging
from storage.minio_storage import (
    data_bronze_leitura,
    ler_parquet_silver,
    salvar_json_bronze_datado,
)

logger = logging.getLogger(__name__)

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

# Validade dos currículos em cache. Sem prazo, o pipeline reutilizaria para
# sempre a cópia antiga de um currículo que o docente já atualizou. 0 desativa.
CACHE_VALIDADE_DIAS = int(os.getenv("LATTES_CACHE_DIAS", "30"))


def expirar_cache(
    diretorio_cvs: Path, validade_dias: int = CACHE_VALIDADE_DIAS, agora: float | None = None
) -> list[str]:
    """Remove currículos em cache mais antigos que `validade_dias`.

    A idade é a data de modificação do arquivo, que o scriptLattes grava ao
    baixar o currículo. Devolve os nomes removidos; o scriptLattes baixa de
    novo, na execução seguinte, apenas esses.
    """
    if validade_dias <= 0 or not diretorio_cvs.is_dir():
        return []
    limite = (agora if agora is not None else time.time()) - validade_dias * 86400
    expirados: list[str] = []
    for arquivo in sorted(diretorio_cvs.iterdir()):
        if arquivo.is_file() and arquivo.stat().st_mtime < limite:
            arquivo.unlink()
            expirados.append(arquivo.name)
    return expirados


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


def enviar_jsons(diretorio_json: Path, prefixo_saida: str, data: str) -> int:
    """Envia os JSONs já renderizados pelo scriptLattes para o MinIO.

    Os currículos são gravados na pasta de data da coleta que a Silver lê (a do
    cadastro de onde saíram os ids), não na data de hoje: assim todas as
    entradas de uma execução da Silver ficam numa única pasta de data.

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
            logger.info(f"Ignorando arquivo sem ID Lattes no nome: {arquivo.name}")
            continue
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        salvar_json_bronze_datado(
            f"{prefixo_saida}/{id_lattes.group(1)}.json", dados, data=data
        )
        enviados += 1

    return enviados


def executar_lattes(
    entrada_silver: str = DEFAULT_ENTRADA_SILVER,
    prefixo_saida: str = DEFAULT_PREFIXO_SAIDA,
    limite: int = 0,
) -> None:
    """Função utilizada pelo Airflow e pela CLI."""
    if not SCRIPTLATTES_PYTHON.is_file() or not SCRIPTLATTES_EXECUTAVEL.is_file():
        raise FileNotFoundError(
            "scriptLattes não encontrado ou sem venv em "
            f"{SCRIPTLATTES_DIR}. Esperado: {SCRIPTLATTES_PYTHON}"
        )

    linhas = gerar_lista_lattes(ler_parquet_silver(entrada_silver), limite)
    if not linhas:
        raise RuntimeError(
            "Nenhum professor com ID Lattes válido foi encontrado na Silver."
        )

    data_coleta_bronze = data_bronze_leitura()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    expirados = expirar_cache(CACHE_DIR / "cvs")
    if expirados:
        logger.info(
            "%d currículo(s) em cache com mais de %d dia(s) serão baixados de novo.",
            len(expirados),
            CACHE_VALIDADE_DIAS,
        )
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

    # A saída do scriptLattes é muito verbosa (centenas de linhas DEBUG por
    # currículo) e escondia o resumo do pipeline; vai para um arquivo próprio.
    arquivo_log = CACHE_DIR / "scriptlattes.log"
    logger.info(
        "Baixando %d currículo(s) com scriptLattes (log em %s)...",
        len(linhas),
        arquivo_log,
    )
    try:
        with arquivo_log.open("w", encoding="utf-8") as log:
            subprocess.run(
                [
                    str(SCRIPTLATTES_PYTHON),
                    str(SCRIPTLATTES_EXECUTAVEL),
                    str(arquivo_config),
                ],
                cwd=SCRIPTLATTES_DIR,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
    except subprocess.CalledProcessError:
        enviados_parciais = enviar_jsons(
            diretorio_saida / "json", prefixo_saida.rstrip("/"), data_coleta_bronze
        )
        logger.warning(
            f"AVISO: o scriptLattes falhou no meio da execução (provável rate limit do "
            f"CNPq). {enviados_parciais} currículo(s) já baixado(s) foram enviados ao "
            f"MinIO antes do erro. O cache foi preservado em {CACHE_DIR} — rode o comando "
            "novamente para continuar de onde parou."
        )
        raise

    enviados = enviar_jsons(
        diretorio_saida / "json", prefixo_saida.rstrip("/"), data_coleta_bronze
    )
    if not enviados:
        raise RuntimeError("Nenhum JSON válido do scriptLattes foi enviado ao MinIO.")

    logger.info(f"{enviados} currículo(s) enviado(s) para bronze/{prefixo_saida.rstrip('/')}.")


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
    configurar_logging()

    executar_lattes(
        entrada_silver=args.entrada_silver,
        prefixo_saida=args.prefixo_saida,
        limite=args.limite,
    )


if __name__ == "__main__":
    main()
