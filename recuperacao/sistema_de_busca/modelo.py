from FlagEmbedding import BGEM3FlagModel
from recuperacao.sistema_de_busca.config import EMBEDDING_MODEL

def carregar_modelo():
    return BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=True)

def gerar_embeddings(modelo, perfis: list[dict], batch_size: int = 16) -> dict[str, dict]:
    """{id do perfil: {"dense": ndarray(1024), "sparse": {token_id: peso}}}"""
    if not perfis:
        return {}

    saida = modelo.encode(
        [p["texto"] for p in perfis],
        batch_size=batch_size,
        return_dense=True,
        return_sparse=True,
    )

    return {
        p["id"]: {
            "dense": saida["dense_vecs"][i],
            "sparse": saida["lexical_weights"][i],
        }
        for i, p in enumerate(perfis)
    }
    
def embedar_consulta(modelo, texto: str) -> dict:
    saida = modelo.encode([texto], return_dense=True, return_sparse=True)
    return {"dense": saida["dense_vecs"][0], "sparse": saida["lexical_weights"][0]}