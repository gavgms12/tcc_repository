import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector, models, Distance, VectorParams, SparseVectorParams
from dotenv import load_dotenv
from recuperacao.sistema_de_busca.config import VECTOR_SIZE
from recuperacao.sistema_de_busca import config
import os
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException
import time

load_dotenv()

def qdrant_id(id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{id}"))

def conectar_Qdrant():
    return QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))

def upsert_com_retry(client, collection_nome: str, pontos: list, tentativas: int = 4) -> None:
    for tentativa in range(1, tentativas + 1):
        try:
            client.upsert(collection_name=collection_nome, points=pontos, wait=True)
            return
        except ResponseHandlingException as erro:      # conexão caiu ou expirou
            if tentativa == tentativas:
                raise
            espera = 2 ** tentativa
            print(f"  Falha de conexão ({erro}). Nova tentativa em {espera}s...")
            time.sleep(espera)
            
def checar_conexao(client):
    collections = client.get_collections()
    print(f"Connected to Qdrant Cloud: {len(collections.collections)} collections")
    
def criar_collection_qdrant(client_qdrant, collection_nome):
    client_qdrant.create_collection(
        collection_name= collection_nome,
        vectors_config={
            "dense": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)},
        sparse_vectors_config={
            "sparse": SparseVectorParams(),
        },
        hnsw_config=models.HnswConfigDiff(
                m=0,  # Bulk load fast: m=0 (build links after ingest).
                ef_construct=100,  # Build quality: used after we set m>0
                full_scan_threshold=10,  # force HNSW instead of full scan
        ),
    )

# aplica filtro do payload antes da busca (colocar antes de adicionar dados)
def criacao_payload_filter(client, collection, field, tipo = models.PayloadSchemaType.INTEGER):
    client.create_payload_index(
        collection_name=collection,
        field_name=field,
        field_schema=tipo,
    )
    
def garantir_colecao(client, nome: str, campos_inteiros: tuple[str, ...] = ()) -> None:
    if not client.collection_exists(nome):
        client.create_collection(
            collection_name=nome,
            vectors_config={"dense": VectorParams(size=config.VECTOR_SIZE, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )
        for campo in campos_inteiros:
            client.create_payload_index(
                collection_name=nome,
                field_name=campo,
                field_schema=models.PayloadSchemaType.INTEGER,
            )

def upsert_perfis(client: QdrantClient, collection_nome: str, perfis: list[dict],
                  embeddings: dict[str, dict], lote: int = 50) -> None:
    pontos = []
    for p in perfis:
        emb = embeddings[p["id"]]
        pontos.append(PointStruct(
            id=qdrant_id(p["id"]),
            vector={
                "dense": emb["dense"].tolist(),
                "sparse": SparseVector(
                    indices=[int(k) for k in emb["sparse"]],
                    values=[float(v) for v in emb["sparse"].values()],
                ),
            },
            payload={"id": p["id"], "hash": p["hash"], "texto": p["texto"], **p["metadata"]},
        ))

    for i in range(0, len(pontos), lote):
        upsert_com_retry(client, collection_nome, pontos[i:i + lote])
    
def deletar_collection(client, classe=''):
    client.delete_collection(classe)

def filtrar_alterados(client: QdrantClient, collection_nome: str, perfis: list[dict], lote: int = 200) -> list[dict]:
    """Devolve só os perfis novos ou cujo hash mudou."""
    alterados = []
    for i in range(0, len(perfis), lote):
        parte = perfis[i:i + lote]
        existentes = client.retrieve(
            collection_name=collection_nome,
            ids=[qdrant_id(p["id"]) for p in parte],
            with_payload=["hash"],
            with_vectors=False,
        )
        hash_salvo = {str(r.id): (r.payload or {}).get("hash") for r in existentes}

        alterados.extend(
            p for p in parte
            if hash_salvo.get(qdrant_id(p["id"])) != p["hash"]
        )
    return alterados

from qdrant_client.models import Fusion, FusionQuery, Prefetch


def busca_hibrida(client, collection_nome: str, emb: dict, limit: int,
                  campos=("id", "nome", "titulo", "professor_ids", "tipo"), filtro=None):
    """Busca densa + esparsa com fusão RRF. Não traz o texto (só os campos pedidos)."""
    if not client.collection_exists(collection_nome):
        return []

    sparse = SparseVector(
        indices=[int(k) for k in emb["sparse"]],
        values=[float(v) for v in emb["sparse"].values()],
    )
    resultado = client.query_points(
        collection_name=collection_nome,
        prefetch=[
            Prefetch(query=emb["dense"].tolist(), using="dense", limit=limit, filter=filtro),
            Prefetch(query=sparse, using="sparse", limit=limit, filter=filtro),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=limit,
        with_payload=list(campos),
    )
    return resultado.points


def buscar_payloads(client, nome: str, ids) -> dict[str, dict]:
    """Payload completo (com `texto`) de ids específicos. Uma chamada em lote."""
    ids = list(dict.fromkeys(str(i) for i in ids))
    if not ids or not client.collection_exists(nome):
        return {}
    registros = client.retrieve(
        collection_name=nome,
        ids=[qdrant_id(i) for i in ids],
        with_payload=["id", "texto", "titulo", "nome", "tipo"],
        with_vectors=False,
    )
    return {str(r.payload["id"]): r.payload for r in registros}

def filtro_ano(ano_min: int | None = None, ano_max: int | None = None) -> models.Filter | None:
    if ano_min is None and ano_max is None:
        return None
    return models.Filter(must=[
        models.FieldCondition(
            key="ano",
            range=models.Range(gte=ano_min, lte=ano_max),   # None means "no limit on that side"
        )
    ])
def atualizar_m(m, client, collection_name):
    client.update_collection(
        collection_name=collection_name,
        hnsw_config=models.HnswConfigDiff(
            m=m
        ),
    )
