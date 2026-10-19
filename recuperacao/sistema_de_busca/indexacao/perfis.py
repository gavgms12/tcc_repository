
from recuperacao.sistema_de_busca.textos import (
    disciplina_montar_texto_para_modelo,
    producao_montar_texto_para_modelo,
    professor_montar_texto_para_modelo,
    gerar_hash
)

# alterar para novo dado

def criar_perfils_trabalhos(trabalhos) -> list[dict]:
    trabalhos_texto = []
    for trabalho in trabalhos:
        texto_embedding = producao_montar_texto_para_modelo(trabalho)
        trabalho_transformado = {
            "id" : trabalho['id'], 
            "hash" : gerar_hash(texto_embedding),
            "texto_embedding": texto_embedding,
            "metadata" : {
               "titulo": trabalho['titulo'],
               "ano" : int(trabalho['ano']),
               "tipo": trabalho.get("tipo")
            }
        }
        trabalhos_texto.append(trabalho_transformado)
        
    return trabalhos_texto

def criar_perfils_professor(professores) -> list[dict]:
    perfis_texto = []
    for professor in professores:
        texto_embedding = professor_montar_texto_para_modelo(professor)
        professor_transformado = {
            "id" : professor['siape'], 
            "hash" : gerar_hash(texto_embedding),
            "texto_embedding": texto_embedding,
            "metadata" : {
               "nome": professor['nome'],
            }
        }
        perfis_texto.append(professor_transformado)

    return perfis_texto


def criar_perfils_disciplinas(disciplinas) -> list[dict]:
    disciplina_texto = []
    for disciplina in disciplinas:
        texto_embedding = disciplina_montar_texto_para_modelo(disciplina)
        trabalho_transformado = {
            "id" : disciplina['idSigaa'], 
            "hash" : gerar_hash(texto_embedding),
            "texto_embedding": texto_embedding,
            "metadata" : {
               "nome": disciplina['nome'],
               "codigo": disciplina["codigo"]

            }
        }
        disciplina_texto.append(trabalho_transformado)
        
    return disciplina_texto

def criar_perfis(registros, montar_texto, id_campo, campos_metadata):
      perfis = []
      for r in registros:
          texto = montar_texto(r)
          perfis.append({
              "id": r[id_campo],
              "hash": gerar_hash(texto),
              "texto_embedding": texto,
              "metadata": {k: r.get(k) for k in campos_metadata} | {"texto": texto},
          })
      return perfis
  
#   perfis_prof = criar_perfis(professores, montar_texto_perfil_professor, "siape", ["nome"])
