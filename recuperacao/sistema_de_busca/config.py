from dotenv import load_dotenv
from FlagEmbedding import BGEM3FlagModel

load_dotenv()

EMBEDDING_MODEL = 'BAAI/bge-m3'
RERANKER_MODEL  = 'BAAI/bge-reranker-v2-m3'
VECTOR_SIZE     = 1024

COLLECTION_DISCIPLINAS = "disciplina"
COLLECTION_PROFESSORES = "perfil_professores"
COLLECTION_ICS = "iniciacao_cientifica"
COLLECTION_PROJETOS = "projetos"

LIMIT_PROFESSORES = 50
FINAL_PROFESSOR_K = 10
PESO_PROFESSOR = 0.20

LIMIT_PROJETOS = 50
# tipo -> de onde vem, quantos resultados buscar, quantos usar por professor, peso
FONTES_ITENS = {
    "trabalho":   {"collection": COLLECTION_ICS,         "limit": 50,  "n": 3, "peso": 0.30},
    "projeto":    {"collection": COLLECTION_PROJETOS,    "limit": 50,  "n": 3, "peso": 0.30},
    "disciplina": {"collection": COLLECTION_DISCIPLINAS, "limit": 100, "n": 3, "peso": 0.20},
}

PESO_TIPO_PROJETO = {
    "pesquisa": 1.0,
    "desenvolvimento": 0.8,
    "extensao": 0.6,
}
PESO_TIPO_PADRAO = 0.7

def peso_do_item(payload: dict) -> float:
    tipo = payload.get("tipo")
    if tipo is None:
        return 1.0
    return PESO_TIPO_PROJETO.get(tipo, PESO_TIPO_PADRAO)