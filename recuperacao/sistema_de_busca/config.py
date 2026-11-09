from pathlib import Path
from dotenv import load_dotenv
from FlagEmbedding import BGEM3FlagModel

#rodar windows senha docker -> docker logs tcc-airflow 2>&1 | Select-String "Password"

load_dotenv()

EMBEDDING_MODEL = 'BAAI/bge-m3'
RERANKER_MODEL  = 'BAAI/bge-reranker-v2-m3'
VECTOR_SIZE     = 1024

# Cache em disco das notas do reranker (preenchido por indexacao/prerankear.py).
# None desliga o cache em disco.
RERANK_CACHE_PATH = str(Path(__file__).resolve().parent / "cache" / "rerank_scores.sqlite")
# venv\Scripts\python.exe -m recuperacao.sistema_de_busca.comparar_modos
# venv\Scripts\python.exe -m recuperacao.sistema_de_busca.indexacao.prerankear --topicos "Matemática Discreta" --modo partes


def texto_topico(nome: str) -> str:
    """Texto do tópico usado na BUSCA (o mesmo em teste e pré-cálculo).

    Tópico como texto -> o próprio texto. Tópico estruturado -> a "descricao".
    """
    topico = TOPICOS[nome]
    texto = topico["descricao"] if isinstance(topico, dict) else topico
    return texto.lower()


def subtopicos_topico(nome: str) -> list[str] | None:
    """Subtópicos usados pelo RERANKER no modo "partes" (None se o tópico for só texto)."""
    topico = TOPICOS.get(nome)
    if isinstance(topico, dict) and topico.get("subtopicos"):
        return [t.lower() for t in topico["subtopicos"]]
    return None


# Corte do reranking (por tópico). Um item passa se:
#   rerank_bruto >= MIN_RERANK_RELATIVO * (maior rerank_bruto da referência)
#   E rerank_bruto >= MIN_RERANK_ABSOLUTO
#   OU for o melhor item daquele tipo para o professor (se MANTER_MELHOR_POR_TIPO)
# Referência: CORTE_POR_TIPO = True  -> melhor item do MESMO tipo (orientação x orientação...)
#             CORTE_POR_TIPO = False -> melhor item do tópico, qualquer tipo (a disciplina costuma dominar)
MIN_RERANK_RELATIVO = 0.10
CORTE_POR_TIPO = True
MIN_RERANK_ABSOLUTO = 0.0
MANTER_MELHOR_POR_TIPO = False

# Itens mantidos só pela regra "melhor do tipo" contam no score, mas são evidência fraca.
# False -> não aparecem na lista do ranking final (só um aviso de quantos foram ocultados).
MOSTRAR_EVIDENCIA_FRACA = False

# Corte de professores no ranking final: só entra quem tiver
#   rerank_score >= MIN_SCORE_PROFESSOR_RELATIVO * (rerank_score do 1º colocado)
MIN_SCORE_PROFESSOR_RELATIVO = 0

# Consulta usada no reranking (a busca continua usando o texto completo do tópico):
#   "texto"  -> texto completo do tópico (comportamento antigo)
#   "nome"   -> só o nome do tópico (ex.: "grafos")
#   "partes" -> nome + cada parte da ementa separada; o item fica com o MAIOR score
RERANK_CONSULTA = "partes"

COLLECTION_DISCIPLINAS = "disciplina"
COLLECTION_PROFESSORES = "perfil_professores"
COLLECTION_ICS = "iniciacao_cientifica"
COLLECTION_PROJETOS = "projetos"
COLLECTION_PRODUCAO = "producao"
COLLECTION_ORIENTADOR = "orientacoes"

# Cada tópico pode ser:
#   - texto: usado na busca e (modo "partes") quebrado em ";" e "." para o reranker
#   - dict:  "descricao" (busca) + "subtopicos" (reranker, modo "partes") + "ementa" (só referência)
TOPICOS = {
    "Compiladores": "compiladores: autômato de estados finitos e expressões regulares, análise léxica, sintática, top-down e bottom-up",
    "Linguagens formais": "linguagens formais: autômatos. autômatos finitos. linguagens regulares. finitos determinísticos e não-determiníticos. linguagens regulares. linguagens livres de contexto. linguagens sensíveis ao contexto.",
    "Grafos": {
        # busca: 1-3 frases focadas
        "descricao": "teoria dos grafos e algoritmos em grafos: modelagem de problemas com vértices e arestas, "
                     "caminhos, conectividade, fluxos e aplicações em redes e bancos de dados orientados a grafos",
        # reranker (modo "partes"): frases curtas que fazem sentido sozinhas
        "subtopicos": [
            "algoritmos de caminho mínimo em grafos (dijkstra, bellman-ford, floyd-warshall)",
            "busca em largura e em profundidade em grafos e ordenação topológica",
            "árvores geradoras mínimas",
            "fluxo máximo e corte mínimo em grafos",
            "conectividade, cortes e componentes fortemente conexas em grafos",
            "bancos de dados orientados a grafos",
            "grafos",
            "graph theory and graph algorithms",
        ],
        # ementa original (só referência, não é usada)
        "ementa": "grafos: conexidade: grafos conexos e cortes. algoritmos de busca em largura, em profundidade e ordenação topológica. árvores geradoras e seus algoritmos. fluxos em redes. algoritmos para caminhos mínimos: dijkstra, bellman-ford, floyd-warshall. componentes fortemente conexas.",
    },
    "Matemática Discreta": {
        "descricao": "fundamentos matemáticos da computação: lógica, conjuntos, combinatória, relações, "
                     "álgebra booleana e técnicas de demonstração",
        "subtopicos": [
            "lógica proposicional e lógica de primeira ordem",
            "técnicas de demonstração e indução matemática",
            "teoria dos conjuntos e operações entre conjuntos",
            "relações de equivalência e relações de ordem",
            "análise combinatória, permutações e princípio da contagem",
            "álgebra booleana",
            "matemática discreta",
            "teoria dos números e criptografia",
            "discrete mathematics, logic and combinatorics",
        ],
        "ementa": "matemática discreta: noções de lógica matemática. conjuntos. operações entre conjuntos. relações. funções ou aplicações. técnicas de demonstração. análise combinatória. lógica de primeira ordem. ordens totais e parciais. álgebra booleana. sistemas algébricos.",
    },
    "Engenharia de Dados": {
        "descricao": "engenharia de dados: coleta, integração, armazenamento e processamento de grandes volumes de dados, "
                     "pipelines de dados, data warehouse e data lake, processamento distribuído e em fluxo",
        "subtopicos": [
            "pipelines de dados e processos de extração, transformação e carga (etl)",
            "data warehouse, data lake e modelagem dimensional",
            "processamento distribuído de big data (hadoop, spark)",
            "processamento de dados em fluxo e streaming em tempo real",
            "integração de dados e qualidade de dados",
            "bancos de dados relacionais e nosql para grandes volumes de dados",
            "computação em nuvem para armazenamento e processamento de dados",
            "engenharia de dados",
            "data engineering, big data and data pipelines",
        ],
    },
    "Programação Embarcada": {
        "descricao": "sistemas embarcados e programação de microcontroladores: software para hardware com recursos "
                     "limitados, sensores e atuadores, sistemas de tempo real e internet das coisas",
        "subtopicos": [
            "programação de microcontroladores (arduino, esp32, arm, pic)",
            "sistemas operacionais de tempo real (rtos) e sistemas de tempo real",
            "interfaces com sensores e atuadores, periféricos e protocolos de comunicação (i2c, spi, uart)",
            "internet das coisas (iot) e dispositivos conectados",
            "programação em c para sistemas embarcados e firmware",
            "arquitetura de hardware embarcado, fpga e sistemas digitais",
            "eficiência energética e otimização em dispositivos embarcados",
            "sistemas embarcados",
            "embedded systems, microcontrollers and firmware programming",
        ],
    },
}

LIMIT_PROFESSORES = 15

# Peso de cada posição na média dos n melhores itens de um professor (pré-ranking e reranking).
#   "nenhum"      1, 1, 1, ...            (média simples)
#   "linear"      n, n-1, ..., 1          (o antigo 3-2-1)
#   "log"         1/log2(pos+1)           (como no nDCG)
#   "harmonico"   1/pos
#   "exponencial" 0.5^(pos-1)
DECAIMENTO = "log"
FINAL_PROFESSOR_K = 15

# tipo -> de onde vem, quantos resultados buscar, quantos usar por professor, peso

PESO_PROFESSOR = 0.15

FONTES_ITENS = {
    "producao": {
        "collection":COLLECTION_PRODUCAO,
        "limit": 120,
        "n": 5,
        "peso_global": 0.44,
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
        "peso_global": 0.15,
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
        "peso_global": 0.13,
        "pesos_internos": {
            "padrao": 1.0
        },
        "filtra_ano": True
    },
    "trabalho": {
        "collection": COLLECTION_ICS, 
        "limit": 50, 
        "n": 2, 
        "peso_global": 0.11,
        "pesos_internos": {
            "padrao": 1.0 
        },
        "filtra_ano": True
    },
    "disciplina": {
        "collection": COLLECTION_DISCIPLINAS, 
        "limit": 100, 
        "n": 3, 
        "peso_global": 0.02,
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