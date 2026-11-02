"""Acesso ao Data Lake MinIO para as camadas Bronze, Silver e Gold.

Cada camada é uma instância de `Camada`; as funções `salvar_*`/`ler_*` no fim
do módulo são atalhos que preservam a API usada pelos scripts.

A Bronze é gravada com data de coleta no caminho e no nome do arquivo:

    chave lógica: raw/sigaa/professores_sigaa.json
    chave real:   raw/20261015/sigaa/professores_sigaa_20261015.json

Silver e Gold leem só a pasta de data mais recente (`ler_json_bronze_recente`);
as coletas anteriores ficam preservadas. Os coletores da própria Bronze, que
reaproveitam dados de coletas passadas (caches), usam a última versão de cada
chave, onde quer que esteja (`ler_json_bronze_ultima_versao`).
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from io import BytesIO
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import boto3
import numpy as np
import pandas as pd
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BRONZE_BUCKET = os.getenv("MINIO_BRONZE_BUCKET", "bronze")
SILVER_BUCKET = os.getenv("MINIO_SILVER_BUCKET", "silver")
GOLD_BUCKET = os.getenv("MINIO_GOLD_BUCKET", "gold")

PREFIXO_RAW = "raw/"
PREFIXO_RUNS = "runs/"
_CHAVE_DATADA = re.compile(r"^raw/(\d{8})/(?:(.+)/)?([^/]+)_(\d{8})(\.[A-Za-z0-9]+)$")
_ERROS_PERMISSAO = {"403", "AccessDenied"}


# --------------------------------------------------------------------------- #
# Chaves datadas (Bronze)
# --------------------------------------------------------------------------- #
def _fuso_coleta() -> timezone | ZoneInfo:
    """Fuso em que a data da coleta é contada (padrão: America/Sao_Paulo).

    O container do Airflow roda em UTC; sem fixar o fuso, uma coleta feita à
    noite no Brasil cairia na pasta do dia seguinte.
    """
    nome = os.getenv("TZ_COLETA", "America/Sao_Paulo")
    try:
        return ZoneInfo(nome)
    except ZoneInfoNotFoundError:  # sem tzdata na imagem: Brasil sem horário de verão
        return timezone(timedelta(hours=-3))


def data_coleta() -> str:
    """Data da coleta (AAAAMMDD). `DATA_COLETA` permite fixá-la (Airflow, testes)."""
    return os.getenv("DATA_COLETA") or datetime.now(_fuso_coleta()).strftime("%Y%m%d")


def chave_datada(chave_logica: str, data: str | None = None) -> str:
    """raw/sigaa/x.json -> raw/20261015/sigaa/x_20261015.json"""
    if not chave_logica.startswith(PREFIXO_RAW):
        raise ValueError(f"Chave Bronze deve começar com '{PREFIXO_RAW}': {chave_logica}")
    data = data or data_coleta()
    pasta, _, arquivo = chave_logica[len(PREFIXO_RAW):].rpartition("/")
    nome, ponto, extensao = arquivo.rpartition(".")
    if not ponto:
        nome, extensao = arquivo, ""
    arquivo_datado = f"{nome}_{data}" + (f".{extensao}" if extensao else "")
    partes = ["raw", data] + ([pasta] if pasta else []) + [arquivo_datado]
    return "/".join(partes)


def chave_logica_de(chave_real: str) -> tuple[str, str] | None:
    """Inverso de `chave_datada`: devolve (chave lógica, data) ou None."""
    match = _CHAVE_DATADA.match(chave_real)
    if not match or match.group(1) != match.group(4):
        return None
    pasta = f"{match.group(2)}/" if match.group(2) else ""
    return f"raw/{pasta}{match.group(3)}{match.group(5)}", match.group(1)


# --------------------------------------------------------------------------- #
# Cliente
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _cliente() -> BaseClient:
    endpoint = os.getenv("MINIO_ENDPOINT")
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")

    for nome, valor in (
        ("MINIO_ENDPOINT", endpoint),
        ("MINIO_ACCESS_KEY", access_key),
        ("MINIO_SECRET_KEY", secret_key),
    ):
        if not valor:
            raise ValueError(f"{nome} não configurado")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv("MINIO_REGION", "us-east-1"),
    )


@contextmanager
def _erros_s3(acao: str, bucket: str, chave: str) -> Iterator[None]:
    try:
        yield
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in _ERROS_PERMISSAO:
            raise PermissionError(
                f"O MinIO recusou {acao} em '{bucket}/{chave}'. Confira "
                "MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY e as "
                "permissões do usuário no bucket."
            ) from erro
        raise


@dataclass(frozen=True)
class Camada:
    """Um bucket do data lake (Bronze, Silver ou Gold)."""

    bucket: str

    def garantir_bucket(self) -> None:
        cliente = _cliente()
        try:
            cliente.head_bucket(Bucket=self.bucket)
        except ClientError as erro:
            codigo = str(erro.response.get("Error", {}).get("Code", ""))
            if codigo in {"404", "NoSuchBucket"}:
                cliente.create_bucket(Bucket=self.bucket)
            elif codigo not in _ERROS_PERMISSAO:
                # Sem ListBucket o HeadBucket falha com 403; deixamos a
                # operação seguinte confirmar a permissão real.
                raise

    def _put(self, chave: str, corpo: bytes, content_type: str) -> None:
        self.garantir_bucket()
        with _erros_s3("a gravação", self.bucket, chave):
            _cliente().put_object(
                Bucket=self.bucket, Key=chave, Body=corpo, ContentType=content_type
            )

    def _get(self, chave: str) -> bytes:
        with _erros_s3("a leitura", self.bucket, chave):
            return _cliente().get_object(Bucket=self.bucket, Key=chave)["Body"].read()

    def existe(self, chave: str) -> bool:
        try:
            _cliente().head_object(Bucket=self.bucket, Key=chave)
        except ClientError as erro:
            if str(erro.response.get("Error", {}).get("Code", "")) in {"404", "NoSuchKey"}:
                return False
            raise
        return True

    def salvar_json(self, chave: str, dados: Any) -> None:
        corpo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        self._put(chave, corpo, "application/json; charset=utf-8")

    def ler_json(self, chave: str) -> Any:
        return json.loads(self._get(chave).decode("utf-8"))

    def listar(self, prefixo: str) -> list[str]:
        chaves: list[str] = []
        with _erros_s3("a listagem", self.bucket, prefixo):
            for pagina in _cliente().get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=prefixo
            ):
                chaves.extend(obj["Key"] for obj in pagina.get("Contents", []))
        return chaves

    def listar_pastas(self, prefixo: str) -> list[str]:
        """Pastas imediatas sob `prefixo` (uma requisição, sem varrer o bucket)."""
        pastas: list[str] = []
        with _erros_s3("a listagem", self.bucket, prefixo):
            for pagina in _cliente().get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=prefixo, Delimiter="/"
            ):
                pastas.extend(p["Prefix"] for p in pagina.get("CommonPrefixes", []))
        return pastas

    def remover(self, chaves: list[str]) -> None:
        for chave in chaves:
            with _erros_s3("a remoção", self.bucket, chave):
                _cliente().delete_object(Bucket=self.bucket, Key=chave)

    def salvar_parquet(self, chave: str, registros: list[dict[str, Any]]) -> None:
        if not registros:
            raise ValueError("Não é possível gravar um Parquet sem registros.")
        buffer = BytesIO()
        pd.DataFrame(registros).to_parquet(buffer, engine="pyarrow", index=False)
        self._put(chave, buffer.getvalue(), "application/vnd.apache.parquet")

    def ler_parquet(self, chave: str) -> list[dict[str, Any]]:
        dataframe = pd.read_parquet(BytesIO(self._get(chave)), engine="pyarrow")
        return [_normalizar_valores(r) for r in dataframe.to_dict(orient="records")]


BRONZE = Camada(BRONZE_BUCKET)
SILVER = Camada(SILVER_BUCKET)
GOLD = Camada(GOLD_BUCKET)


# --------------------------------------------------------------------------- #
# Bronze: gravação datada e leitura da versão mais recente
# --------------------------------------------------------------------------- #
def salvar_json_bronze_datado(
    chave_logica: str, dados: Any, data: str | None = None
) -> str:
    """Grava `dados` na Bronze com a data da coleta e devolve a chave real."""
    chave = chave_datada(chave_logica, data)
    BRONZE.salvar_json(chave, dados)
    return chave


def datas_bronze() -> list[str]:
    """Datas de coleta existentes na Bronze (AAAAMMDD), da mais nova à mais antiga."""
    pastas = BRONZE.listar_pastas(PREFIXO_RAW)
    datas = (p.removeprefix(PREFIXO_RAW).rstrip("/") for p in pastas)
    return sorted((d for d in datas if re.fullmatch(r"\d{8}", d)), reverse=True)


def data_bronze_leitura() -> str:
    """Data lida pela Silver: a pasta mais recente da Bronze.

    `BRONZE_DATA` fixa outra data (reprocessar uma coleta antiga).
    """
    fixa = os.getenv("BRONZE_DATA")
    if fixa:
        return fixa
    datas = datas_bronze()
    if not datas:
        raise FileNotFoundError("A Bronze não tem nenhuma pasta de coleta em 'raw/'.")
    return datas[0]


def ler_json_bronze_recente(chave_logica: str, data: str | None = None) -> Any:
    """Lê uma chave lógica da pasta de data mais recente da Bronze.

    Falha, em vez de recorrer a uma data mais antiga, se a chave não estiver
    nessa pasta: misturar coletas de dias diferentes esconderia uma coleta
    incompleta.
    """
    data = data or data_bronze_leitura()
    chave = chave_datada(chave_logica, data)
    try:
        return BRONZE.ler_json(chave)
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {"404", "NoSuchKey"}:
            raise FileNotFoundError(
                f"'{chave_logica}' não existe na coleta {data} da Bronze "
                f"({chave}). Rode a coleta que o gera nessa data, ou fixe outra "
                "com BRONZE_DATA."
            ) from erro
        raise


def chaves_bronze_da_data(
    prefixo_logico: str, data: str | None = None
) -> dict[str, str]:
    """Chave lógica -> chave real dos objetos sob `prefixo_logico` na data."""
    data = data or data_bronze_leitura()
    chaves: dict[str, str] = {}
    for chave in BRONZE.listar(f"{PREFIXO_RAW}{data}/"):
        resolvida = chave_logica_de(chave)
        if resolvida and resolvida[0].startswith(prefixo_logico):
            chaves[resolvida[0]] = chave
    return chaves


def ler_json_bronze_ultima_versao(chave_logica: str) -> Any:
    """Última versão de uma chave lógica, em qualquer data (mais nova primeiro).

    Para coletores que reaproveitam o que já coletaram antes (caches) ou que
    dependem de outra coleta da Bronze, sem exigir que estejam na mesma pasta.
    """
    for data in datas_bronze():
        chave = chave_datada(chave_logica, data)
        if BRONZE.existe(chave):
            return BRONZE.ler_json(chave)
    raise FileNotFoundError(f"Nenhuma versão de '{chave_logica}' na Bronze.")


def ler_json_bronze_ultima_versao_ou_none(chave_logica: str) -> Any | None:
    try:
        return ler_json_bronze_ultima_versao(chave_logica)
    except FileNotFoundError:
        return None


# --------------------------------------------------------------------------- #
# Atalhos por camada
# --------------------------------------------------------------------------- #
def salvar_json_bronze(chave: str, dados: Any) -> None:
    BRONZE.salvar_json(chave, dados)


def ler_json_bronze(chave: str) -> Any:
    return BRONZE.ler_json(chave)


def listar_chaves_bronze(prefixo: str) -> list[str]:
    return BRONZE.listar(prefixo)


def salvar_json_gold(chave: str, dados: Any) -> None:
    GOLD.salvar_json(chave, dados)


def ler_json_gold(chave: str) -> Any:
    return GOLD.ler_json(chave)


def listar_chaves_gold(prefixo: str) -> list[str]:
    return GOLD.listar(prefixo)


def salvar_parquet_silver(chave: str, registros: list[dict[str, Any]]) -> None:
    SILVER.salvar_parquet(chave, registros)


def ler_parquet_silver(chave: str) -> list[dict[str, Any]]:
    return SILVER.ler_parquet(chave)

def _normalizar_valores(valor: Any) -> Any:
    """Converte para tipos nativos do Python o que o pandas/pyarrow devolve.

    Colunas do tipo lista em Parquet sempre voltam do pyarrow como
    numpy.ndarray por célula (mesmo com engine="pyarrow"), não como list
    nativa. Isso quebra json.dumps, isinstance(x, list) e comparações.
    Também substitui NaN escalar (campos opcionais ausentes) por None.
    """
    if isinstance(valor, np.ndarray):
        return [_normalizar_valores(item) for item in valor.tolist()]
    if isinstance(valor, list):
        return [_normalizar_valores(item) for item in valor]
    if isinstance(valor, dict):
        return {chave: _normalizar_valores(item) for chave, item in valor.items()}
    if isinstance(valor, float) and pd.isna(valor):
        return None
    return valor

_RUN_GOLD = re.compile(r"\d{8}T\d{6}Z")


def ultima_run_gold() -> str:
    """Prefixo da run mais recente da Gold, ex.: 'runs/20261020T002154Z/'.

    `GOLD_RUN` fixa uma run específica (reprocessar, testes).
    """
    fixa = os.getenv("GOLD_RUN")
    if fixa:
        return f"{PREFIXO_RUNS}{fixa}/"

    runs = [
        p for p in GOLD.listar_pastas(PREFIXO_RUNS)
        if _RUN_GOLD.fullmatch(p.rstrip("/").rsplit("/", 1)[-1])
    ]
    if not runs:
        raise FileNotFoundError(f"A Gold não tem nenhuma run em '{PREFIXO_RUNS}'.")
    return max(runs)   # timestamp ISO: o maior é o mais novo


def ler_jsons_gold(prefixo: str) -> list[dict[str, Any]]:
    """Lê todos os .json sob `prefixo` na Gold e devolve a lista de dicts."""
    if not prefixo.endswith("/"):
        prefixo += "/"

    registros: list[dict[str, Any]] = []
    for chave in sorted(listar_chaves_gold(prefixo)):
        if not chave.lower().endswith(".json"):
            continue
        try:
            dado = GOLD.ler_json(chave)
        except Exception as erro:
            logger.warning("Ignorando %s: %s", chave, erro)
            continue
        if isinstance(dado, dict):
            registros.append(dado)
        else:
            logger.warning("Ignorando %s: não é um objeto JSON", chave)
    return registros

def ler_jsons_soltos_gold(prefixo: str) -> dict[str, Any]:
    """Lê os .json diretamente em `prefixo` (sem subpastas).

    Devolve {nome do arquivo sem extensão: conteúdo}.
    """
    if not prefixo.endswith("/"):
        prefixo += "/"

    arquivos: dict[str, Any] = {}
    for chave in sorted(GOLD.listar_arquivos(prefixo)):
        if not chave.lower().endswith(".json"):
            continue
        nome = chave.rsplit("/", 1)[-1].removesuffix(".json")
        arquivos[nome] = GOLD.ler_json(chave)
    return arquivos