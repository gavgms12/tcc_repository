
from qdrant_client.models import Prefetch, FusionQuery, Fusion, models
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, SparseVectorParams
from qdrant_client.models import PointStruct, SparseVector
import uuid

def conectar_qdrant(url):
    return QdrantClient(url=url)

def criar_banco_qdrant(client_qdrant):
    client_qdrant.create_collection(
        collection_name="professores",
        vectors_config={
            "dense": VectorParams(size=1024, distance=Distance.COSINE)},
        sparse_vectors_config={
            "sparse": SparseVectorParams(),
        },
    )

def adicionar_professores_qdrant(client_qdrant, perfis, embeddings_professores, lexical_professores):
    points = []
    for professor, dense, sparse in zip(perfis, embeddings_professores, lexical_professores):
        sparse_indices = [int(k) for k in sparse.keys()]
        sparse_values = [float(v) for v in sparse.values()]

        points.append(
            PointStruct(
                id=int(professor["id"]),
                vector={
                    "dense": dense.tolist(),
                    "sparse": SparseVector(indices=sparse_indices, values=sparse_values),
                },
                # metadados
                payload={
                    "nome": professor.get("nome"),
                    "unidade": professor.get("unidade"),
                    "hash": professor.get("hash")
                    
                }
            )
        )
        
    client_qdrant.upsert(collection_name="professores", points=points)

    
def verificar_alteracao_hash(perfils,client_qdrant):
    # fazer consulta no Q drant e verificar alteração no hash ou não
    perfis_para_atualizar = []
    for perfil in perfils:
        busca = client_qdrant.retrieve(
            collection_name="professores",
            ids=[int(perfil.get("id"))],
            with_payload=True
        )
        if busca:
            payload_qdrant = busca[0].payload
            hash_salvo = payload_qdrant.get("hash")
            versao_salva = payload_qdrant.get("versão")
            
            if hash_salvo != perfil.get("hash") or versao_salva != perfil.get("versão"):
                perfis_para_atualizar.append(perfil)
        
        else:
            perfis_para_atualizar.append(perfil)
        
    return perfis_para_atualizar

def busca_densa(client_qdrant,embedding_aluno,collection = "professores"):
    return client_qdrant.query_points(
        collection,
        query=embedding_aluno,
        using="dense",
        limit=10,
    )
    
def busca_esparsa(client_qdrant, lexical_aluno):
    sparse_query = SparseVector(
    indices=[int(k) for k in lexical_aluno.keys()],
    values=[float(v) for v in lexical_aluno.values()],
    )

    return client_qdrant.query_points(
        "professores",
        query=sparse_query,
        using="sparse",
        limit=10,
    )


def busca_hibrida(client_qdrant, aluno, professor):