from dotenv import load_dotenv
from FlagEmbedding import BGEM3FlagModel

load_dotenv()

EMBEDDING_MODEL = 'BAAI/bge-m3'
RERANKER_MODEL  = 'BAAI/bge-reranker-v2-m3'
VECTOR_SIZE     = 1024
MIN_RERANK = 0.005
COLLECTION_DISCIPLINAS = "disciplina"
COLLECTION_PROFESSORES = "perfil_professores"
COLLECTION_ICS = "iniciacao_cientifica"
COLLECTION_PROJETOS = "projetos"
COLLECTION_PRODUCAO = "producao"
COLLECTION_ORIENTADOR = "orientacoes"

TOPICOS = {
    "Compiladores": "compiladores: autômato de estados finitos e expressões regulares, Análise léxica, sintática, top-down e bottom-up",
    "Linguagens formais": "linguagens formais: autômatos. autômatos finitos. linguagens regulares. finitos determinísticos e não-determiníticos. linguagens Regulares. linguagens livres de contexto. linguagens sensíveis ao contexto. máquinas de Turing.",
    "Grafos": "teoria dos grafos: algoritmos em grafos, caminhos, conectividade, coloração",
}

LIMIT_PROFESSORES = 50
FINAL_PROFESSOR_K = 10
# tipo -> de onde vem, quantos resultados buscar, quantos usar por professor, peso

# O professor continua valendo 0.20
PESO_PROFESSOR = 0.20  

FONTES_ITENS = {
    "producao": {
        "collection":COLLECTION_PRODUCAO,
        "limit": 120,
        "n": 5,
        "peso_global": 0.43,
        "pesos_internos": {
            "livro": 1.0,               # 125/125
            "artigo_periodico": 0.8,    # 100/125
            "capitulo_livro": 0.2,      # 25/125
            "trabalho_congresso": 0.04, # 5/125
            "resumo_expandido": 0.04,   # 5/125
            "padrao": 0.5
        },
        "filtra_ano": True
    },
    "projeto": {
        "collection": COLLECTION_PROJETOS, 
        "limit": 50, 
        "n": 3, 
        "peso_global": 0.14,
        "pesos_internos": {
            "pesquisa": 1.0, 
            "desenvolvimento": 1.0, 
            "extensao": 1.0, 
            "padrao": 1.0
        },
        "filtra_ano": True
    },
    "orientacao": {
        "collection":COLLECTION_ORIENTADOR, 
        "limit": 120, 
        "n": 3, 
        "peso_global": 0.12,
        "pesos_internos": {
            "padrao": 1.0
        },
        "filtra_ano": True
    },
    "trabalho": {
        "collection": COLLECTION_ICS, 
        "limit": 50, 
        "n": 2, 
        "peso_global": 0.10,
        "pesos_internos": {
            "padrao": 1.0 
        },
        "filtra_ano": True
    },
    "disciplina": {
        "collection": COLLECTION_DISCIPLINAS, 
        "limit": 100, 
        "n": 5, 
        "peso_global": 0.01,
        "pesos_internos": {
            "padrao": 1.0
        },
        "filtra_ano": False
    }
}

def peso_global(fonte: str) -> float:
    return FONTES_ITENS[fonte]["peso_global"]


def peso_interno(fonte: str, payload: dict) -> float:
    """Multiplicador do score de um item conforme o subtipo (payload["tipo"])."""
    pesos = FONTES_ITENS[fonte].get("pesos_internos", {})
    return pesos.get(payload.get("tipo"), pesos.get("padrao", 1.0))