from __future__ import annotations
import json
import hashlib
import re

def _limpar(texto) -> str:
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    return re.sub(r"\.{2,}$", ".", texto)

def gerar_hash(componentes):   
    json_normalizado = json.dumps(
        componentes,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":")
    )
    return hashlib.sha256(transformar_bytes(json_normalizado)).hexdigest()

def transformar_bytes(texto : str) -> bytes:
    t = texto
    return t.encode("utf-8")

def ics_montar_texto_para_modelo(producao):
    partes = []

    titulo = _limpar(producao.get("titulo"))
    if titulo:
        partes.append(f"Título: {titulo}")
        
    resumo = _limpar(producao.get("titulo"))
    
    if resumo:
        partes.append(f"Resumo: {resumo}")

    if producao.get("palavrasChaves"):
        partes.append(
            f"Palavras-chave: {', '.join(producao['palavrasChaves'])}"
        )

    return "\n".join(partes)

#adicionar competencias e outros conteúdos

def professor_montar_texto_para_modelo(perfil):

    partes = []
    
    resumo = _limpar(perfil.get("resumo"))
    if resumo:
        partes.append(f"Resumo: {resumo}")
    
    formacao_academica = _limpar(perfil.get("formacaoAcademicaProfissional"))
    if formacao_academica:
        partes.append(
            f"Formação Profissional Acadêmica: "
            f"{formacao_academica}"
        )

    areas_especializacao=_limpar(perfil.get("areasEspecializacao"))
    if areas_especializacao:
        partes.append(
            f"Áreas de Especialização: "
            f"{', '.join(areas_especializacao)}"
        )    
    topicos_interesse= _limpar(perfil.get("topicosInteresse"))
    if topicos_interesse:
        partes.append(
            f"Tópicos de Interesse: "
            f"{', '.join(topicos_interesse)}"
        )  
    
    return "\n".join(partes)

def disciplina_montar_texto_para_modelo(disciplina):
    partes = []

    materia = _limpar(disciplina.get("nome"))
    if materia:
        partes.append(f"Nome: {materia}")

    ementa = _limpar(disciplina.get("ementa"))
    if ementa:
        partes.append(f"Ementa: {ementa}")

    return "\n".join(partes)


ROTULO_TIPO = {
    "pesquisa": "Projeto de pesquisa",
    "extensao": "Projeto de extensão",
    "desenvolvimento": "Projeto de desenvolvimento",
}


def projeto_montar_texto_para_modelo(projeto: dict) -> str:
    partes = []

    nome = _limpar(projeto.get("nome"))
    if nome:
        partes.append(f"Título: {nome}")

    tipo = projeto.get("tipo")
    if tipo:
        partes.append(f"Tipo: {ROTULO_TIPO.get(tipo, f'Projeto de {tipo}')}")

    descricao = _limpar(projeto.get("descricao"))
    if descricao:
        partes.append(f"Descrição: {descricao}")

    return "\n".join(partes)