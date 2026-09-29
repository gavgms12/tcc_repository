
from __future__ import annotations
import argparse
from pymongo import MongoClient
from datetime import datetime, timezone
import hashlib


def obter_dados_banco() -> list[str]:
    client = MongoClient("mongodb://localhost:27017/")
    db = client["TCC"]
    professores = db["Docentes"]
    perfis = list(professores.find({}))
    return perfis 

def normalizar_texto(texto: str) -> str:
    return " ".join(texto.lower().split())

def montagem_perfil(prof) -> str:
    nomes_disciplinas = [d["nome"] for d in prof.get("disciplinasSigaa", [])]
    disciplinas_text = ", ".join(nomes_disciplinas)
    
    return (
        f""" Nome: {prof.get('nome', '')} Disciplinas: {disciplinas_text.lower()}"""
        )
    
def extrair_areas(professor):
    competencias = professor.get("competencias", {})
    areas = competencias.get("areas", [])

    grandes_areas = set()
    areas_atuacao = set()
    subareas = set()

    for item in areas:
        grande_area = item.get("grande_area")
        area = item.get("area")
        subarea = item.get("subarea")

        if grande_area:
            grandes_areas.add(grande_area)

        if area:
            areas_atuacao.add(area)

        if subarea:
            subareas.add(subarea)

    return {
        "grandes_areas": sorted(grandes_areas),
        "areas": sorted(areas_atuacao),
        "subareas": sorted(subareas)
    }
    
def transformar_bytes(texto : str) -> bytes:
    t = texto
    return t.encode("utf-8")

def criar_perfils(professores) -> list[dict]:
    professores_texto = []
    for professor in professores:
        perfil_embedding = normalizar_texto(montagem_perfil(professor))
        professor = {
            "id" : professor.get("siape"),
            "nome" : professor.get("nome"),
            "texto_embedding" : perfil_embedding,
            "hash" : hashlib.sha256(transformar_bytes(perfil_embedding)).hexdigest(),
            "metadata" : {
                **extrair_areas(professor),
                "unidade" : professor.get("unidade"),
            }
        }
        professores_texto.append(professor)
        
    return professores_texto

def formatar_texto_aluno(aluno):
    return (
            f""" Área: {aluno.get('area', '')} descrição: {aluno.get('descricao','')}"""
            )

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Criação dos perfis dos professores para utilização no modelo BGE-M3."
    )
    professores = obter_dados_banco()
    perfis = criar_perfils(professores)
    
    print(f"Criação de {len(perfis)} perfis de professores.")
    print(f"Coletado em: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()