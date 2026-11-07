from __future__ import annotations
import json
import hashlib
import re

def _limpar(texto) -> str:
    texto = re.sub(r"\s+", " ", str(texto or "")).strip().lower()
    return re.sub(r"\.{2,}$", ".", texto)

def _juntar_lista(valores) -> str:
    return ", ".join(_limpar(v).lower() for v in valores or [] if _limpar(v))

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
        
    resumo = _limpar(producao.get("resumo"))
    
    if resumo:
        partes.append(f"Resumo: {resumo}")

    palavras_chave = _juntar_lista(producao.get("palavrasChaves"))
    if palavras_chave:
        partes.append(f"Palavras-chave: {palavras_chave}")

    return "\n".join(partes)

#adicionar competencias e outros conteúdos

def professor_montar_texto_para_modelo(perfil):

    partes = []
    
    resumo = _limpar(perfil.get("resumo"))
    if resumo:
        partes.append(f"Resumo: {resumo}")
    
    # formacao_academica = _limpar(perfil.get("formacaoAcademicaProfissional"))
    # if formacao_academica:
    #     partes.append(
    #         f"Formação Profissional Acadêmica: "
    #         f"{formacao_academica}"
    #     )
    
    areas_especializacao = _juntar_lista(perfil.get("areasEspecializacao"))
    if areas_especializacao:
        partes.append(f"Áreas de Especialização: {areas_especializacao}")

    topicos_interesse = _juntar_lista(perfil.get("topicosInteresse"))
    if topicos_interesse:
        partes.append(f"Tópicos de Interesse: {topicos_interesse}")

    
    return "\n".join(partes)

def projeto_montar_texto_para_modelo(projeto: dict) -> str:
    partes = []

    nome = _limpar(projeto.get("nome"))
    if nome:
        partes.append(f"Título: {nome}")


    descricao = _limpar(projeto.get("descricao"))
    if descricao:
        partes.append(f"Descrição: {descricao}")

    return "\n".join(partes)

def producao_montar_texto_para_modelo(producao: dict) -> str:
    partes = []

    titulo = _limpar(producao.get("titulo"))
    if titulo:
        partes.append(f"Título: {titulo}")

    return "\n".join(partes)

def disciplina_montar_texto_para_modelo(disciplina: dict) -> str:
    partes = []

    nome = _limpar(disciplina.get("nome"))
    if nome:
        partes.append(f"Nome: {nome}")
    ementa = _limpar(disciplina.get("ementa"))
    if nome:
        partes.append(f"Ementa: {ementa}")
    return "\n".join(partes)

def orientacao_montar_texto_para_modelo(orientacao: dict) -> str:
    partes = []

    titulo = _limpar(orientacao.get("titulo"))
    if titulo:
        partes.append(f"Título: {titulo}")

    return "\n".join(partes)