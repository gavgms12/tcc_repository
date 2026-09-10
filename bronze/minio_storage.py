"""Acesso ao Data Lake MinIO para as camadas Bronze e Silver."""

from __future__ import annotations

import json
import os
from io import BytesIO
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BRONZE_BUCKET = os.getenv("MINIO_BRONZE_BUCKET", "bronze")
SILVER_BUCKET = os.getenv("MINIO_SILVER_BUCKET", "silver")


def _cliente() -> BaseClient:
    """Cria um cliente compatível com S3 apontado para o MinIO."""
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
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
        if str(erro.response.get("Error", {}).get("Code", "")) in {"403", "AccessDenied"}:
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
        if str(erro.response.get("Error", {}).get("Code", "")) in {"403", "AccessDenied"}:
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
        if str(erro.response.get("Error", {}).get("Code", "")) in {"403", "AccessDenied"}:
            raise PermissionError(
                f"O MinIO recusou a listagem de '{BRONZE_BUCKET}/{prefixo}'. "
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
        if str(erro.response.get("Error", {}).get("Code", "")) in {"403", "AccessDenied"}:
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
        if str(erro.response.get("Error", {}).get("Code", "")) in {"403", "AccessDenied"}:
            raise PermissionError(
                f"O MinIO recusou a leitura de '{SILVER_BUCKET}/{chave}'. "
                "Conceda a permissão s3:GetObject ao usuário configurado."
            ) from erro
        raise

    dataframe = pd.read_parquet(BytesIO(resposta["Body"].read()), engine="pyarrow")
    return dataframe.where(pd.notna(dataframe), None).to_dict(orient="records")
