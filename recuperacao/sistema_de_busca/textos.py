from __future__ import annotations
import json
import hashlib

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

#rever para novo jeito que tá o dado

def producao_montar_texto_para_modelo(producao):
    partes = []

    if producao.get("titulo"):
        partes.append(f"Título: {producao['titulo']}")

    if producao.get("resumo"):
        partes.append(f"Resumo: {producao['resumo']}")

    if producao.get("palavrasChaves"):
        partes.append(
            f"Palavras-chave: {', '.join(producao['palavrasChaves'])}"
        )

    return "\n".join(partes)

def montar_texto_competencias(competencias):
    partes = []

    areas = competencias.get("areas")

    if areas is not None and len(areas) > 0:
        textos_areas = []

        for area in areas:
            campos = []

            if area.get("grande_area"):
                campos.append(f"Grande área: {area['grande_area']}")

            if area.get("area"):
                campos.append(f"Área: {area['area']}")

            if area.get("subarea"):
                campos.append(f"Subárea: {area['subarea']}")

            if area.get("especialidade"):
                campos.append(f"Especialidade: {area['especialidade']}")

            if campos:
                textos_areas.append(". ".join(campos))

        if textos_areas:
            partes.append(
                "Áreas de conhecimento:\n" +
                "\n".join(textos_areas)
            )

    linhas = competencias.get("linhas_pesquisa")

    if linhas is not None and len(linhas) > 0:
        partes.append(
            "Linhas de pesquisa: " + ", ".join(linhas)
        )

    palavras_chave = competencias.get("palavras_chave")

    if palavras_chave is not None and len(palavras_chave) > 0:
        partes.append(
            "Palavras-chave: " + ", ".join(palavras_chave)
        )

    return "\n\n".join(partes)

def professor_montar_texto_para_modelo(perfil):

    partes = []
    
    if perfil.get("resumo"):
        partes.append(f"Resumo: {perfil['resumo']}")
    
    if perfil.get("formacaoAcademicaProfissional"):
        partes.append(
            f"Formação Profissional Acadêmica: "
            f"{perfil['formacaoAcademicaProfissional']}"
        )

    if perfil.get("areasInteresse").any():
        partes.append(
            f"Áreas de Interesse: "
            f"{', '.join(perfil['areasInteresse'])}"
        )    
    if perfil.get("competencias"):
        competencias_texto = montar_texto_competencias(
            perfil["competencias"]
        )
        if competencias_texto:
            partes.append(competencias_texto)
    
    return "\n".join(partes)

def disciplina_montar_texto_para_modelo(disciplina):
    partes = []

    if disciplina.get("nome"):
        partes.append(f"Nome: {disciplina['nome']}")

    if disciplina.get("ementa"):
        partes.append(f"Ementa: {disciplina['ementa']}")

    return "\n".join(partes)
