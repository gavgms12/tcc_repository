"""Fixtures: um cliente S3 em memória no lugar do MinIO."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage import minio_storage


class S3Falso:
    """Implementa só o que `Camada` usa do cliente boto3."""

    def __init__(self) -> None:
        self.objetos: dict[tuple[str, str], bytes] = {}

    def head_bucket(self, Bucket):  # noqa: N803
        return {}

    def create_bucket(self, Bucket):  # noqa: N803
        return {}

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.objetos[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.objetos:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

        class Corpo:
            def __init__(self, dados: bytes) -> None:
                self.dados = dados

            def read(self) -> bytes:
                return self.dados

        return {"Body": Corpo(self.objetos[(Bucket, Key)])}

    def head_object(self, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.objetos:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objetos.pop((Bucket, Key), None)

    def get_paginator(self, _nome):
        outer = self

        class Paginador:
            def paginate(self, Bucket, Prefix="", Delimiter=None):  # noqa: N803
                chaves = sorted(
                    k for b, k in outer.objetos if b == Bucket and k.startswith(Prefix)
                )
                if Delimiter:
                    pastas = sorted(
                        {Prefix + k[len(Prefix):].split(Delimiter)[0] + Delimiter
                         for k in chaves if Delimiter in k[len(Prefix):]}
                    )
                    chaves = [k for k in chaves if Delimiter not in k[len(Prefix):]]
                    yield {"Contents": [{"Key": k} for k in chaves],
                           "CommonPrefixes": [{"Prefix": p} for p in pastas]}
                else:
                    yield {"Contents": [{"Key": k} for k in chaves]}

        return Paginador()


@pytest.fixture
def s3(monkeypatch) -> S3Falso:
    falso = S3Falso()
    monkeypatch.setattr(minio_storage, "_cliente", lambda: falso)
    monkeypatch.setenv("DATA_COLETA", "20261015")
    return falso
