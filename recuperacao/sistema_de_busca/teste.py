from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant
from recuperacao.sistema_de_busca.modelo import carregar_modelo
from recuperacao.sistema_de_busca.busca.reranking import carregar_reranker
from recuperacao.sistema_de_busca.busca.service import Recomendador
from recuperacao.sistema_de_busca.busca.exibicao import imprimir_ranking
from recuperacao.sistema_de_busca import config

modelo = carregar_modelo()
reranker = carregar_reranker()
client = conectar_Qdrant()

try:
    rec = Recomendador(client, modelo, reranker)
    selecionados = ["Compiladores", "Linguagens formais"]   # vindos dos checkboxes
    topicos = {t: config.TOPICOS[t].lower() for t in selecionados}
    # texto livre opcional: topicos["Texto livre"] = "..."
    imprimir_ranking(rec.recomendar(topicos, top_k=8, debug=True), ", ".join(topicos))

finally:
    client.close()