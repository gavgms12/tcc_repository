from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant
from recuperacao.sistema_de_busca.modelo import carregar_modelo
from recuperacao.sistema_de_busca.busca.reranking import carregar_reranker
from recuperacao.sistema_de_busca.busca.service import Recomendador
from recuperacao.sistema_de_busca.busca.exibicao import imprimir_ranking

modelo = carregar_modelo()
reranker = carregar_reranker()
client = conectar_Qdrant()

try:
    rec = Recomendador(client, modelo, reranker)
    consulta = (
        "Gostaria de desenvolver um projeto com inteligência artificial embarcada, "
        "rodando modelos de machine learning em microcontroladores de baixo consumo."
    )    
    imprimir_ranking(rec.recomendar(consulta, top_k=10), consulta)
finally:
    client.close()