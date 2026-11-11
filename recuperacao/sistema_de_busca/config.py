import os
from pathlib import Path
from dotenv import load_dotenv
from FlagEmbedding import BGEM3FlagModel

#rodar windows senha docker -> docker logs tcc-airflow 2>&1 | Select-String "Password"

load_dotenv()

EMBEDDING_MODEL = 'BAAI/bge-m3'
RERANKER_MODEL  = 'BAAI/bge-reranker-v2-m3'
VECTOR_SIZE     = 1024

# Cache em disco das notas do reranker (preenchido por indexacao/prerankear.py).
# None desliga o cache em disco. A variável de ambiente RERANK_CACHE_PATH troca o caminho (usada no Colab).
RERANK_CACHE_PATH = os.getenv("RERANK_CACHE_PATH") or str(Path(__file__).resolve().parent / "cache" / "rerank_scores.sqlite")
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
    "Sistemas Embarcados": {
      "categoria": "Eletrônica",
      "descricao": "projeto de hardware e software para sistemas dedicados: microcontroladores, firmware, programação embarcada e sistemas de tempo real",
      "subtopicos": [
        "microcontroladores e microprocessadores",
        "programação embarcada em C",
        "firmware e drivers de periféricos",
        "sistemas operacionais de tempo real (RTOS)",
        "Arduino, ESP32, ARM e STM32",
        "embedded systems, firmware, real-time systems"
      ],
      "disciplinas": [
        "Microcontroladores e Microprocessadores",
        "Laboratório de Microcontroladores e Microprocessadores",
        "Laboratório de Programação Embarcada",
        "Sistemas Operacionais"
      ]
    },
    "Inteligência Artificial": {
      "categoria": "Computação",
      "descricao": "métodos que permitem a sistemas aprender com dados e tomar decisões: aprendizado de máquina, redes neurais, lógica fuzzy e visão computacional",
      "subtopicos": [
        "aprendizado de máquina e aprendizado profundo",
        "redes neurais artificiais",
        "lógica fuzzy e sistemas de inferência",
        "visão computacional e processamento de imagens",
        "modelos de linguagem (LLM)",
        "TinyML e IA embarcada",
        "machine learning, deep learning, neural networks, computer vision"
      ],
      "disciplinas": [
        "Inteligência Artificial",
        "TinyML - Aprendizado de Máquina Aplicado para Dispositivos IoT Embarcados"
      ]
    },
    "Internet das Coisas": {
      "categoria": "Eletrônica",
      "descricao": "dispositivos conectados que coletam e trocam dados: sensores, comunicação sem fio, plataformas IoT e computação de borda",
      "subtopicos": [
        "redes de sensores sem fio",
        "protocolos IoT: MQTT, LoRa, Zigbee, BLE",
        "computação de borda (edge computing)",
        "monitoramento remoto e telemetria",
        "Internet of Things, wireless sensor networks, edge computing"
      ],
      "disciplinas": [
        "TinyML - Aprendizado de Máquina Aplicado para Dispositivos IoT Embarcados"
      ]
    },
    "Engenharia Biomédica": {
      "categoria": "Eletrônica",
      "descricao": "tecnologia aplicada à saúde: instrumentação biomédica, sinais fisiológicos, equipamentos médicos e engenharia clínica",
      "subtopicos": [
        "instrumentação biomédica",
        "sinais fisiológicos: ECG, EEG e EMG",
        "equipamentos eletromédicos e engenharia clínica",
        "usabilidade de equipamentos médicos",
        "circuitos integrados para aplicações biomédicas",
        "biomedical engineering, medical devices, eHealth"
      ],
      "disciplinas": [
        "Instrumentação Biomédica II",
        "Tópicos Especiais em Engenharia Clínica",
        "Gestão em Tecnologias Médicas I",
        "Gestão em Tecnologias Médicas II"
      ]
    },
    "Sistemas de Controle": {
      "categoria": "Controle e Energia",
      "descricao": "modelagem e controle de sistemas dinâmicos: controle clássico e moderno, controle robusto, identificação de sistemas e controle multivariável",
      "subtopicos": [
        "modelagem e análise de sistemas dinâmicos",
        "controle clássico: PID, lugar das raízes e resposta em frequência",
        "controle robusto e controle H-infinito",
        "controle multivariável e controle preditivo (MPC)",
        "identificação de sistemas",
        "sistemas não lineares",
        "control systems, robust control, system identification"
      ],
      "disciplinas": [
        "Sistemas de Controle",
        "Laboratório de Sistemas de Controle",
        "Modelagem e Análise de Sistemas Dinâmicos",
        "Laboratório de Controle Clássico",
        "Controle Multivariável"
      ]
    },
    "Automação Industrial": {
      "categoria": "Controle e Energia",
      "descricao": "automação de processos e máquinas na indústria: CLPs, sistemas supervisórios, redes industriais e instrumentação industrial",
      "subtopicos": [
        "controladores lógicos programáveis (CLP)",
        "sistemas supervisórios SCADA",
        "redes industriais: Profibus, Modbus, Ethernet industrial",
        "instrumentação industrial",
        "Indústria 4.0 e manutenção preditiva",
        "industrial automation, PLC, SCADA"
      ],
      "disciplinas": [
        "Automação de Sistemas",
        "Automação e Supervisão de Processos I",
        "Redes Industriais",
        "Laboratório de Instrumentação Industrial I",
        "Banco de Dados para Automação"
      ]
    },
    "Sistemas Distribuídos e Nuvem": {
      "categoria": "Computação",
      "descricao": "sistemas que rodam em várias máquinas: computação paralela, computação em nuvem, clusters e arquiteturas orientadas a serviços",
      "subtopicos": [
        "sistemas distribuídos e simulação distribuída",
        "computação paralela e de alto desempenho",
        "computação em nuvem (cloud computing)",
        "contêineres e orquestração: Docker e Kubernetes",
        "arquitetura orientada a serviços (SOA) e web services",
        "distributed systems, parallel computing, cloud computing"
      ],
      "disciplinas": [
        "Sistemas Distribuídos",
        "Laboratório de Sistemas Distribuídos",
        "Tópicos Especiais em Sistemas Distribuídos",
        "Processamento Paralelo (Prática)"
      ]
    },
    "Processamento de Sinais": {
      "categoria": "Eletrônica",
      "descricao": "análise e tratamento de sinais: filtragem digital, análise espectral, transformadas e condicionamento de sinais",
      "subtopicos": [
        "processamento digital de sinais (DSP)",
        "filtros digitais",
        "transformada de Fourier e transformada wavelet",
        "condicionamento de sinais",
        "processamento de sinais biomédicos",
        "digital signal processing, filtering, wavelets"
      ],
      "disciplinas": [
        "Processamento Digital de Sinais",
        "Sinais e Sistemas",
        "Introdução à Análise de Sinais",
        "Condicionamento de Sinais"
      ]
    },
    "Segurança da Informação": {
      "categoria": "Computação",
      "descricao": "proteção de sistemas e dados: criptografia, cibersegurança, análise de vulnerabilidades e privacidade",
      "subtopicos": [
        "criptografia",
        "segurança de redes e cibersegurança",
        "análise de vulnerabilidades",
        "segurança em sistemas de automação industrial",
        "privacidade e LGPD",
        "information security, cybersecurity, cryptography"
      ],
      "disciplinas": [
        "Criptografia e Segurança de Dados",
        "Tópicos Especiais em Segurança da Informação",
        "Introdução à Proteção e Segurança de Dados"
      ]
    },
    "Eletrônica de Potência": {
      "categoria": "Controle e Energia",
      "descricao": "conversão e controle de energia elétrica com dispositivos eletrônicos: conversores, inversores, filtros ativos e acionamentos",
      "subtopicos": [
        "conversores CC-CC e CA-CC",
        "inversores e conversores multiníveis",
        "filtros ativos de potência e FACTS",
        "acionamentos elétricos controlados",
        "transferência de energia sem fio",
        "power electronics, converters, inverters"
      ],
      "disciplinas": [
        "Fundamentos de Eletrônica de Potência",
        "Eletrônica de Potência e Acionamentos Controlados",
        "Eletrônica de Potência Aplicada a Sistemas Elétricos",
        "Laboratório de Conversores Eletrônicos de Potência"
      ]
    },
    "Sistemas Digitais e FPGA": {
      "categoria": "Eletrônica",
      "descricao": "projeto de circuitos e sistemas digitais: FPGA, linguagens de descrição de hardware e arquitetura de computadores",
      "subtopicos": [
        "circuitos digitais e lógica sequencial",
        "FPGA e síntese lógica",
        "Verilog e VHDL",
        "arquitetura de computadores e RISC-V",
        "verificação de sistemas digitais",
        "digital design, FPGA, hardware description languages"
      ],
      "disciplinas": [
        "Circuitos Digitais I",
        "Introdução ao Verilog",
        "Arquitetura de Sistemas Digitais",
        "Síntese Lógica",
        "Verificação de Sistemas Digitais",
        "Eletrônica Digital II"
      ]
    },
    "Microeletrônica": {
      "categoria": "Eletrônica",
      "descricao": "projeto de circuitos integrados: tecnologia CMOS, circuitos integrados analógicos e digitais, layout e fabricação",
      "subtopicos": [
        "projeto de circuitos integrados CMOS",
        "circuitos integrados analógicos",
        "circuitos integrados digitais",
        "processos de fabricação de circuitos integrados",
        "circuitos neuromórficos e de baixo consumo",
        "microelectronics, CMOS, integrated circuit design, VLSI"
      ],
      "disciplinas": [
        "Introdução à Microeletrônica",
        "Projeto de Circuitos Integrados Analógicos",
        "Projeto de Circuitos Integrados Digitais",
        "Referências CMOS de Tensão e Corrente"
      ]
    },
    "Redes de Computadores": {
      "categoria": "Computação",
      "descricao": "comunicação entre computadores e dispositivos: protocolos, arquitetura de redes, redes móveis e redes industriais",
      "subtopicos": [
        "protocolos de comunicação e TCP/IP",
        "redes móveis e 5G",
        "redes definidas por software (SDN)",
        "redes industriais",
        "computer networks, network protocols"
      ],
      "disciplinas": [
        "Redes de Computadores",
        "Laboratório de Redes de Computadores",
        "Redes de Comunicação para Processos",
        "Redes Industriais"
      ]
    },
    "Desenvolvimento Web e Mobile": {
      "categoria": "Computação",
      "descricao": "criação de aplicações para navegadores e dispositivos móveis: front-end, back-end, APIs e aplicativos",
      "subtopicos": [
        "desenvolvimento web front-end e back-end",
        "aplicativos Android e iOS",
        "APIs REST e web services",
        "JavaScript e WebAssembly",
        "web development, mobile apps"
      ],
      "disciplinas": []
    },
    "Eletrônica Analógica e Instrumentação": {
      "categoria": "Eletrônica",
      "descricao": "circuitos eletrônicos analógicos e medição: amplificadores, sensores, condicionamento e instrumentos de medida",
      "subtopicos": [
        "amplificadores operacionais",
        "circuitos eletrônicos analógicos",
        "sensores e transdutores",
        "instrumentação eletrônica e medidas elétricas",
        "analog electronics, instrumentation, sensors"
      ],
      "disciplinas": [
        "Eletrônica Analógica I",
        "Eletrônica Analógica II",
        "Eletrônica Básica e Instrumentação",
        "Laboratório de Eletrônica Analógica I"
      ]
    },
    "Energia e Fontes Renováveis": {
      "categoria": "Controle e Energia",
      "descricao": "geração, qualidade e armazenamento de energia elétrica: fontes renováveis, sistemas elétricos de potência e redes inteligentes",
      "subtopicos": [
        "energia solar fotovoltaica",
        "qualidade da energia elétrica",
        "sistemas de armazenamento de energia e baterias",
        "geração distribuída e microrredes",
        "redes elétricas inteligentes (smart grids)",
        "veículos elétricos e carregadores",
        "renewable energy, power quality, energy storage"
      ],
      "disciplinas": [
        "Condicionadores de Energia",
        "Acionamento e Condicionamento de Energia",
        "Automação de Sistemas Elétricos"
      ]
    },
    "Algoritmos, Grafos e Otimização": {
      "categoria": "Computação",
      "descricao": "fundamentos da computação e resolução de problemas: estruturas de dados, análise de algoritmos, teoria dos grafos e otimização",
      "subtopicos": [
        "estruturas de dados",
        "análise e complexidade de algoritmos",
        "teoria dos grafos",
        "otimização e metaheurísticas",
        "matemática discreta",
        "algorithms, graph theory, optimization"
      ],
      "disciplinas": [
        "Estrutura de Dados",
        "Análise de Algoritmos",
        "Teoria dos Grafos",
        "Matemática Discreta"
      ]
    },
    "Engenharia de Software": {
      "categoria": "Computação",
      "descricao": "processos e práticas para construir software de qualidade: requisitos, arquitetura de software, testes e DevOps",
      "subtopicos": [
        "arquitetura de software e microsserviços",
        "requisitos de software",
        "testes de software",
        "métodos ágeis",
        "DevOps e integração contínua",
        "software engineering, software architecture, DevOps"
      ],
      "disciplinas": [
        "Engenharia de Software",
        "Programação Orientada a Objetos",
        "Laboratório de Programação Orientada a Objeto"
      ]
    },
    "Robótica": {
      "categoria": "Controle e Energia",
      "descricao": "projeto e controle de robôs: manipuladores, robôs móveis, drones e manufatura automatizada",
      "subtopicos": [
        "manipuladores robóticos",
        "robôs móveis e veículos autônomos",
        "drones e VANTs",
        "manufatura integrada por computador",
        "robotics, mobile robots, UAV"
      ],
      "disciplinas": [
        "Robótica",
        "Introdução à Robótica",
        "Laboratório de Robótica",
        "Manufatura Integrada por Computador e Robótica"
      ]
    },
    "Telecomunicações e Óptica": {
      "categoria": "Eletrônica",
      "descricao": "transmissão de informação por sinais elétricos, ondas e luz: antenas, radiofrequência, micro-ondas e comunicações ópticas",
      "subtopicos": [
        "antenas e propagação de ondas",
        "radiofrequência e micro-ondas",
        "comunicações ópticas e fotônica",
        "modulação e sistemas de comunicação",
        "redes 5G e rádio sobre fibra",
        "telecommunications, antennas, RF, optical communications"
      ],
      "disciplinas": [
        "Eletromagnetismo",
        "Telecomunicações II",
        "Laboratório de Telecomunicações II"
      ]
    },
    "Dados": {
      "categoria": "Computação",
      "descricao": "armazenamento, processamento e análise de dados: bancos de dados, engenharia de dados e ciência de dados",
      "subtopicos": [
        "bancos de dados relacionais e NoSQL",
        "engenharia de dados e pipelines de dados",
        "big data e armazenamento orientado a colunas",
        "ciência de dados e análise estatística",
        "mineração de dados",
        "databases, data engineering, data science"
      ],
      "disciplinas": [
        "Banco de Dados",
        "Laboratório de Banco de Dados",
        "Banco de Dados para Automação",
        "Metodologia Científica e Análise de Dados"
      ]
    }
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