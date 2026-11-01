import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector, models, Distance, VectorParams, SparseVectorParams
from dotenv import load_dotenv
from recuperacao.sistema_de_busca.config import VECTOR_SIZE
from recuperacao.sistema_de_busca import config
import os
from qdrant_client.http.exceptions import UnexpectedResponse

load_dotenv()

def qdrant_id(id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{id}"))

def conectar_Qdrant():
    return QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
    
def checar_conexao(client):
    collections = client.get_collections()
    print(f"Connected to Qdrant Cloud: {len(collections.collections)} collections")
    
def criar_collection_qdrant(client_qdrant, nome):
    client_qdrant.create_collection(
        collection_name= nome,
        vectors_config={
            "dense": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)},
        sparse_vectors_config={
            "sparse": SparseVectorParams(),
        },
    )

# aplica filtro do payload antes da busca (colocar antes de adicionar dados)
def criacao_payload_filter(client, collection, field, tipo = models.PayloadSchemaType.INTEGER):
    client.create_payload_index(
        collection_name=collection,
        field_name=field,
        field_schema=tipo,
    )
    
def garantir_colecao(client: QdrantClient, nome: str) -> None:
    if client.collection_exists(nome):
        return
    client.create_collection(
        collection_name=nome,
        vectors_config={"dense": VectorParams(size=config.VECTOR_SIZE, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()},
    )
    
def upsert_perfis(client: QdrantClient, nome: str, perfis: list[dict],
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
        try:
            client.upsert(collection_name=nome, points=pontos[i:i + lote], wait=True)
        except UnexpectedResponse as e:
            print("Status:", e.status_code)
            print("Motivo:", e.content.decode("utf-8", errors="replace"))
            raise
    
def deletar_collection(client, classe=''):
    client.delete_collection(classe)

def filtrar_alterados(client: QdrantClient, nome: str, perfis: list[dict], lote: int = 200) -> list[dict]:
    """Devolve só os perfis novos ou cujo hash mudou."""
    alterados = []
    for i in range(0, len(perfis), lote):
        parte = perfis[i:i + lote]
        existentes = client.retrieve(
            collection_name=nome,
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


def busca_hibrida(client, nome: str, emb: dict, limit: int,
                  campos=("id", "nome", "titulo", "professor_ids", "tipo")):
    """Busca densa + esparsa com fusão RRF. Não traz o texto (só os campos pedidos)."""
    if not client.collection_exists(nome):
        return []

    sparse = SparseVector(
        indices=[int(k) for k in emb["sparse"]],
        values=[float(v) for v in emb["sparse"].values()],
    )
    resultado = client.query_points(
        collection_name=nome,
        prefetch=[
            Prefetch(query=emb["dense"].tolist(), using="dense", limit=limit),
            Prefetch(query=sparse, using="sparse", limit=limit),
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
        with_payload=True,
        with_vectors=False,
    )
    return {str(r.payload["id"]): r.payload for r in registros}