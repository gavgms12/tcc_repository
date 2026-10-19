import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector, models, Distance, VectorParams, SparseVectorParams
from dotenv import load_dotenv
from recuperacao.sistema_de_busca.config import VECTOR_SIZE
import os

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
    
def adicionar_disciplinas_qdrant(
    client_qdrant,
    conteudo,
    resultados,
    collection="",
    batch_size=50
):
    points = []

    for objeto in conteudo:

        objeto_id = objeto.get("id")
        resultado = resultados[objeto_id]

        sparse = resultado["sparse"]

        sparse_indices = [int(k) for k in sparse.keys()]
        sparse_values = [float(v) for v in sparse.values()]

        dense = resultado["dense"]

        points.append(
            PointStruct(
                id=qdrant_id(objeto_id),
                vector={
                    "dense": dense.tolist(),
                    "sparse": SparseVector(
                        indices=sparse_indices,
                        values=sparse_values
                    ),
                },
                payload={
                    "id": objeto_id,
                    "nome": objeto.get("metadata", {}).get("nome"),
                    "texto": objeto.get("texto_embedding"),                    
                    "hash": objeto.get("hash")
                }
            )
        )
    #Enviando aos poucos já que tem muitas disciplinas
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]

        client_qdrant.upsert(
            collection_name=collection,
            points=batch,
            wait=True
        )
        
def adicionar_professores_qdrant(client_qdrant, professores, resultados, collection = ""):
    points = []
    for objeto in professores:
        
        objeto_id  = objeto.get('id')
        
        resultado = resultados[objeto_id]

        sparse = resultado["sparse"]

        sparse_indices = [int(k) for k in sparse.keys()]
        sparse_values = [float(v) for v in sparse.values()]
            
        dense = resultado["dense"]
            
        points.append(
            PointStruct(
                id=qdrant_id(objeto.get("id")),
                vector={
                    "dense": dense.tolist(),
                    "sparse": SparseVector(indices=sparse_indices, values=sparse_values),
                },
                # metadados
                payload={
                    "id": objeto.get("id"),
                    "nome":  objeto.get("metadata", {}).get("nome"),
                    "texto": objeto.get("texto_embedding"),
                    "hash" :  objeto.get("hash")
                }
            )
        )
            
    client_qdrant.upsert(collection_name=collection, points=points)

def adicionar_trabalhos_qdrant(client_qdrant, conteudo, resultados, collection = ""):
    points = []
    for objeto in conteudo:
        
        objeto_id  = objeto.get('id')
        
        resultado = resultados[objeto_id]

        sparse = resultado["sparse"]

        sparse_indices = [int(k) for k in sparse.keys()]
        sparse_values = [float(v) for v in sparse.values()]
            
        dense = resultado["dense"]
            
        points.append(
            PointStruct(
                id=qdrant_id(objeto.get("id")),
                vector={
                    "dense": dense.tolist(),
                    "sparse": SparseVector(indices=sparse_indices, values=sparse_values),
                },
                # metadados
                payload={
                    "id": objeto.get("id"),
                    "titulo":  objeto.get("metadata", {}).get("titulo"),
                    "ano": objeto.get("metadata", {}).get("ano"),
                    "texto": objeto.get("texto_embedding"),
                    "hash":objeto.get("hash")
                    
                }
            )
        )
            
    client_qdrant.upsert(collection_name=collection, points=points)
    
def deletar_collection(client, classe=''):
    client.delete_collection(classe)
    