import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector, models, Distance, VectorParams, SparseVectorParams
from dotenv import load_dotenv
from recuperacao.sistema_de_busca.config import VECTOR_SIZE
from recuperacao.sistema_de_busca import config
import os
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException
import time
from concurrent.futures import ThreadPoolExecutor

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

_colecoes_existentes: dict[int, set[str]] = {}


def colecao_existe(client, nome: str) -> bool:
    """Como client.collection_exists, mas lista as coleções uma vez só por client
    (antes era uma ida ao servidor a cada busca). Só consulta de novo se o nome não estiver na lista."""
    existentes = _colecoes_existentes.get(id(client))
    if existentes is None or nome not in existentes:
        existentes = {c.name for c in client.get_collections().collections}
        _colecoes_existentes[id(client)] = existentes
    return nome in existentes


def em_paralelo(tarefas: dict, max_workers: int = 8) -> dict:
    """{chave: função sem argumentos} -> {chave: resultado}, rodando as funções em threads.

    Serve para chamadas de rede (Qdrant): o tempo passa esperando a resposta, não na CPU.
    """
    if not tarefas:
        return {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tarefas))) as pool:
        futuros = {chave: pool.submit(funcao) for chave, funcao in tarefas.items()}
        return {chave: f.result() for chave, f in futuros.items()}


def busca_hibrida(client, collection_nome: str, emb: dict, limit: int,
                  campos=("id", "nome", "titulo", "professor_ids", "tipo"), filtro=None):
    """Busca densa + esparsa com fusão RRF. Não traz o texto (só os campos pedidos)."""
    if not colecao_existe(client, collection_nome):
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
    if not ids or not colecao_existe(client, nome):
        return {}
    registros = client.retrieve(
        collection_name=nome,
        ids=[qdrant_id(i) for i in ids],
        with_payload=["id", "texto", "titulo", "nome", "tipo", "codigo"],
        with_vectors=False,
    )
    return {str(r.payload["id"]): r.payload for r in registros}


def buscar_payloads_varios(client, pedidos: dict[str, list]) -> dict[str, dict[str, dict]]:
    """{coleção: ids} -> {coleção: {id: payload}}, uma chamada por coleção, todas em paralelo."""
    return em_paralelo({
        nome: (lambda nome=nome, ids=ids: buscar_payloads(client, nome, ids))
        for nome, ids in pedidos.items()
    })

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
