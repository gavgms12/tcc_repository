
from FlagEmbedding import BGEM3FlagModel

# bge-m3 vai ficar na mémoria da nossa aplicação
def carregar_bgeM3():
    return BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

def professores_rodar_bgeM3(modelo, perfis):
    texto_professores = []
    for professor in perfis:
        texto_professores.append(professor.get("texto_embedding"))
    return modelo.encode(texto_professores, batch_size=12, max_length=512, return_dense=True, return_sparse=True)

def professores_obter_denso(perfis_transformados):
    return perfis_transformados['dense_vecs']
    
def professores_obter_lexical(perfis_transformados):
    return perfis_transformados["lexical_weights"]

def professores_obter_lexical_denso(perfis_transformados) -> list:
    return [perfis_transformados['dense_vecs'], perfis_transformados["lexical_weights"]]

def aluno_rodar_bgem3(query_aluno, model):
    return model.encode([query_aluno.lower()], return_dense=True, return_sparse=True)

def aluno_obter_lexical(aluno):
    return aluno['lexical_weights'][0]

def aluno_obter_denso(aluno):
    return aluno['dense_vecs'][0]

def aluno_rodar_bgem3_denso_lexical(query_aluno, model) -> list:
    aluno = model.encode([query_aluno.lower()], return_dense=True, return_sparse=True)
    embedding_aluno = aluno['dense_vecs'][0]
    lexical_aluno = aluno['lexical_weights'][0]
    return [embedding_aluno, lexical_aluno]

