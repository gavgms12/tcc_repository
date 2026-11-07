from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant
from recuperacao.sistema_de_busca.modelo import carregar_modelo
from recuperacao.sistema_de_busca.busca.reranking import carregar_reranker
from recuperacao.sistema_de_busca.busca.service import Recomendador
from recuperacao.sistema_de_busca.busca.exibicao import imprimir_comparacao, imprimir_pre_ranking, imprimir_ranking, imprimir_tempos, salvar_em_txt
from recuperacao.sistema_de_busca import config

modelo = carregar_modelo()
reranker = carregar_reranker()
client = conectar_Qdrant()

try:
    rec = Recomendador(client, modelo, reranker)
    selecionados = ["Grafos", "Matemática Discreta"]
    topicos = {t: config.TOPICOS[t].lower() for t in selecionados}
    # texto livre: topicos["Texto livre"] = "..."
    with salvar_em_txt("_".join(topicos)):   # gera recuperacao/output/<data-hora>_<tópicos>.txt
        pre = rec.pre_ranking(topicos, top_k=10)
        imprimir_pre_ranking(pre, ", ".join(topicos))
        imprimir_tempos(rec.tempos, "TEMPOS DO PRÉ-RANKING")

        final = rec.recomendar(topicos, top_k=5, debug=False)
        imprimir_ranking(final, ", ".join(topicos))
        imprimir_tempos(rec.tempos, "TEMPOS DA RECOMENDAÇÃO")
        imprimir_comparacao(pre, final)
        if rec.professores_cortados:
            print("Cortados por score baixo (abaixo do corte relativo ao 1º): " + ", ".join(
                f"{nome} ({score:.6f})" for nome, score in rec.professores_cortados))
        if rec.professores_cortados:
            print("Cortados por score baixo (< corte relativo ao 1º): " + ", ".join(
                f"{nome} ({score:.6f})" for nome, score in rec.professores_cortados))

finally:
    client.close()