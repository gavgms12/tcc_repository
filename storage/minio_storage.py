"""Acesso ao Data Lake MinIO para as camadas Bronze e Silver."""

from __future__ import annotations

import json
import os
from io import BytesIO
from typing import Any

import boto3
import numpy as np
import pandas as pd
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

BRONZE_BUCKET = os.getenv("MINIO_BRONZE_BUCKET", "bronze")
SILVER_BUCKET = os.getenv("MINIO_SILVER_BUCKET", "silver")
GOLD_BUCKET = os.getenv("MINIO_GOLD_BUCKET", "gold")


def _cliente() -> BaseClient:
    endpoint = os.getenv("MINIO_ENDPOINT")
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")

    if not endpoint:
        raise ValueError("MINIO_ENDPOINT não configurado")

    if not access_key:
        raise ValueError("MINIO_ACCESS_KEY não configurado")

    if not secret_key:
        raise ValueError("MINIO_SECRET_KEY não configurado")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv("MINIO_REGION", "us-east-1"),
    )

def _garantir_bucket(cliente: BaseClient, bucket: str) -> None:
    try:
        cliente.head_bucket(Bucket=bucket)
    except ClientError as erro:
        codigo = str(erro.response.get("Error", {}).get("Code", ""))
        if codigo in {"404", "NoSuchBucket"}:
            cliente.create_bucket(Bucket=bucket)
            return

        # Algumas políticas S3/MinIO não concedem ListBucket (necessária para
        # HeadBucket), embora permitam PutObject/GetObject por chave. Nesse
        # caso, deixamos a operação seguinte confirmar a permissão real.
        if codigo in {"403", "AccessDenied"}:
            return
        raise


def salvar_json_bronze(chave: str, dados: Any) -> None:
    """Serializa dados brutos em JSON e os grava no bucket Bronze."""
    cliente = _cliente()
    _garantir_bucket(cliente, BRONZE_BUCKET)
    corpo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    try:
        cliente.put_object(
            Bucket=BRONZE_BUCKET,
            Key=chave,
            Body=corpo,
            ContentType="application/json; charset=utf-8",
        )
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {
            "403",
            "AccessDenied",
        }:
            raise PermissionError(
                f"O MinIO recusou a gravação em '{BRONZE_BUCKET}/{chave}'. "
                "Confira MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY "
                "e a permissão s3:PutObject no bucket."
            ) from erro
        raise


def ler_json_bronze(chave: str) -> Any:
    """Lê e desserializa um JSON bruto a partir do bucket Bronze."""
    try:
        resposta = _cliente().get_object(Bucket=BRONZE_BUCKET, Key=chave)
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {
            "403",
            "AccessDenied",
        }:
            raise PermissionError(
                f"O MinIO recusou a leitura de '{BRONZE_BUCKET}/{chave}'. "
                "Conceda a permissão s3:GetObject ao usuário configurado."
            ) from erro
        raise
    return json.loads(resposta["Body"].read().decode("utf-8"))


def listar_chaves_bronze(prefixo: str) -> list[str]:
    """Lista as chaves existentes no bucket Bronze sob um prefixo."""
    cliente = _cliente()
    chaves: list[str] = []
    paginador = cliente.get_paginator("list_objects_v2")
    try:
        for pagina in paginador.paginate(Bucket=BRONZE_BUCKET, Prefix=prefixo):
            for objeto in pagina.get("Contents", []):
                chaves.append(objeto["Key"])
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {
            "403",
            "AccessDenied",
        }:
            raise PermissionError(
                f"O MinIO recusou a listagem de '{BRONZE_BUCKET}/{prefixo}'. "
                "Conceda a permissão s3:ListBucket ao usuário configurado."
            ) from erro
        raise
    return chaves


def salvar_json_gold(chave: str, dados: Any) -> None:
    """Serializa um perfil unificado em JSON e o grava no bucket Gold."""
    cliente = _cliente()
    _garantir_bucket(cliente, GOLD_BUCKET)
    corpo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    try:
        cliente.put_object(
            Bucket=GOLD_BUCKET,
            Key=chave,
            Body=corpo,
            ContentType="application/json; charset=utf-8",
        )
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {
            "403",
            "AccessDenied",
        }:
            raise PermissionError(
                f"O MinIO recusou a gravação em '{GOLD_BUCKET}/{chave}'. "
                "Confira MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY "
                "e a permissão s3:PutObject no bucket."
            ) from erro
        raise


def ler_json_gold(chave: str) -> Any:
    """Lê e desserializa um perfil unificado a partir do bucket Gold."""
    try:
        resposta = _cliente().get_object(Bucket=GOLD_BUCKET, Key=chave)
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {
            "403",
            "AccessDenied",
        }:
            raise PermissionError(
                f"O MinIO recusou a leitura de '{GOLD_BUCKET}/{chave}'. "
                "Conceda a permissão s3:GetObject ao usuário configurado."
            ) from erro
        raise
    return json.loads(resposta["Body"].read().decode("utf-8"))


def listar_chaves_gold(prefixo: str) -> list[str]:
    """Lista as chaves existentes no bucket Gold sob um prefixo."""
    cliente = _cliente()
    chaves: list[str] = []
    paginador = cliente.get_paginator("list_objects_v2")
    try:
        for pagina in paginador.paginate(Bucket=GOLD_BUCKET, Prefix=prefixo):
            for objeto in pagina.get("Contents", []):
                chaves.append(objeto["Key"])
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {
            "403",
            "AccessDenied",
        }:
            raise PermissionError(
                f"O MinIO recusou a listagem de '{GOLD_BUCKET}/{prefixo}'. "
                "Conceda a permissão s3:ListBucket ao usuário configurado."
            ) from erro
        raise
    return chaves


def salvar_parquet_silver(chave: str, registros: list[dict[str, Any]]) -> None:
    """Grava registros tabulares no bucket Silver no formato Parquet."""
    if not registros:
        raise ValueError("Não é possível gravar um Parquet sem registros.")

    buffer = BytesIO()
    pd.DataFrame(registros).to_parquet(buffer, engine="pyarrow", index=False)

    cliente = _cliente()
    _garantir_bucket(cliente, SILVER_BUCKET)
    try:
        cliente.put_object(
            Bucket=SILVER_BUCKET,
            Key=chave,
            Body=buffer.getvalue(),
            ContentType="application/vnd.apache.parquet",
        )
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {
            "403",
            "AccessDenied",
        }:
            raise PermissionError(
                f"O MinIO recusou a gravação em '{SILVER_BUCKET}/{chave}'. "
                "Conceda a permissão s3:PutObject ao usuário configurado."
            ) from erro
        raise


def ler_parquet_silver(chave: str) -> list[dict[str, Any]]:
    """Lê um Parquet da camada Silver e devolve seus registros."""
    try:
        resposta = _cliente().get_object(Bucket=SILVER_BUCKET, Key=chave)
    except ClientError as erro:
        if str(erro.response.get("Error", {}).get("Code", "")) in {
            "403",
            "AccessDenied",
        }:
            raise PermissionError(
                f"O MinIO recusou a leitura de '{SILVER_BUCKET}/{chave}'. "
                "Conceda a permissão s3:GetObject ao usuário configurado."
            ) from erro
        raise

    dataframe = pd.read_parquet(BytesIO(resposta["Body"].read()), engine="pyarrow")
    registros = dataframe.to_dict(orient="records")
    return [_normalizar_valores(registro) for registro in registros]


def _normalizar_valores(valor: Any) -> Any:
    """Converte para tipos nativos do Python o que o pandas/pyarrow devolve.

    Colunas do tipo lista em Parquet sempre voltam do pyarrow como
    numpy.ndarray por célula (mesmo com engine="pyarrow" e independente de
    .where()) — não como list nativa. Isso quebra json.dumps, isinstance(x,
    list) e comparações em qualquer código que consuma estes registros.
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
