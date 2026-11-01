from BM25 import tokenizer_professores_bm25, busca_bm25
from criacao_texto_professores import obter_dados_banco, obter_dados_banco, criar_perfils

professores_database = obter_dados_banco()

perfis_analise = criar_perfils(professores_database)

