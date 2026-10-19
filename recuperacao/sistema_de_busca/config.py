from dotenv import load_dotenv
from FlagEmbedding import BGEM3FlagModel

load_dotenv()

PESO_DISCIPLINAS = 0.2
PESO_PERFIL = 0.2
PESO_IC = 0.6

EMBEDDING_MODEL = "BAAI/bge-m3"
RERANKER_MODEL  = "BAAI/bge-reranker-v2-m3"
VECTOR_SIZE     = 1024

LIMIT_PROFESSORES = 50
LIMIT_ICS         = 50
LIMIT_DISCIPLINAS = 100
FINAL_PROFESSOR_K = 15
N_TRABALHOS       = 3
N_DISCIPLINAS     = 3