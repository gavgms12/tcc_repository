from FlagEmbedding import BGEM3FlagModel
from recuperacao.sistema_de_busca.config import EMBEDDING_MODEL
from recuperacao.sistema_de_busca.textos import producao_montar_texto_para_modelo
def carregar_modelo():
    return BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=True)

def rodar_modelo(modelo, texto):
    embedding = {}
    resultado = modelo.encode(
        texto,
        return_dense=True, 
        return_sparse=True
    )

    embedding = {
        "dense": resultado["dense_vecs"],
        "sparse": resultado["lexical_weights"]
    }

    return embedding

def criar_representacao_densa_esparso(classe, modelo = carregar_modelo()) -> dict[str,str]:
    objetos_valores_denso_esparso = {}
    for objeto in classe:
         texto_transformado = rodar_modelo(modelo,objeto.get("texto_embedding"))
         objetos_valores_denso_esparso[objeto["id"]] = texto_transformado
    return objetos_valores_denso_esparso
