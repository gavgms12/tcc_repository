#!/usr/bin/env python3
"""Limpa e normaliza os perfis SIGAA na camada Silver (sem unir com o Lattes).

Lê os docentes e componentes curriculares brutos da Bronze e grava, por
siape, um perfil SIGAA podado: sem contato nem o link de Currículo Lattes
duplicado (esses campos simplesmente não são lidos do bruto), disciplinas
reduzidas a IDs de um catálogo de componentes, projetos de pesquisa reduzidos
a nome/área de conhecimento, e produção docente sem atividades de extensão,
filtrada a partir de 2016 e com o título extraído por IA (sem coautores ou
alunos), pronta para embeddings (bge-m3).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bronze.minio_storage import ler_json_bronze, salvar_parquet_silver  # noqa: E402
from ia_titulos import extrair_titulos  # noqa: E402

DEFAULT_DOCENTES_SIGAA = "raw/sigaa/docentes_sigaa.json"
DEFAULT_COMPONENTES_SIGAA = "raw/sigaa/componentes_sigaa.json"
DEFAULT_SAIDA_PERFIS = "perfil_sigaa_limpo.parquet"
DEFAULT_SAIDA_COMPONENTES = "componentes_curriculares.parquet"

PRODUCAO_ANO_MINIMO = 2016
PLACEHOLDERS_AREA_INTERESSE = {"não informadas", "nao informadas", "não informada", "nao informada"}


def normalizar_texto(texto: str | None) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip()


def gerar_id(tipo: str, titulo: str, ano: int | None) -> str:
    base = f"{tipo}|{titulo}|{ano or ''}".lower()
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def limpar_perfil_sigaa(docente_bruto: dict) -> dict:
    """Perfil SIGAA podado: só o que agrega semântica (descarta contatos/URLs).

    O bruto traz `perfil` (seção #perfil-docente) e `contatos` (seção
    #contato); só lemos `perfil`, e dele só descrição pessoal, formação e
    áreas de interesse — o que já remove o `<div id="contato">` e o item
    "Currículo Lattes" (o número do currículo já consta na identidade do
    professor, vinda do merge SIGAA+IESTI).
    """
    perfil = docente_bruto.get("perfil") or {}
    areas_interesse = [
        normalizar_texto(a)
        for a in perfil.get("areasInteresse", [])
        if normalizar_texto(a) and normalizar_texto(a).lower() not in PLACEHOLDERS_AREA_INTERESSE
    ]
    return {
        "descricaoPessoal": normalizar_texto(perfil.get("descricaoPessoal")) or None,
        "formacaoAcademicaProfissional": normalizar_texto(perfil.get("formacaoAcademicaProfissional")) or None,
        "areasInteresse": areas_interesse,
    }


def normalizar_disciplinas(disciplinas_ministradas: list[dict]) -> list[str]:
    """Reduz disciplinas ministradas a uma lista de idSigaa (sem duplicatas)."""
    ids = {d["idSigaa"] for d in disciplinas_ministradas if d.get("idSigaa")}
    return sorted(ids)


def construir_catalogo_disciplinas(
    componentes_payload: dict,
    docentes_payload: dict,
) -> list[dict]:
    """Catálogo de disciplinas por idSigaa: parte do catálogo oficial do
    departamento e complementa com disciplinas de outros departamentos que os
    docentes lecionam mas que não aparecem em componentes_sigaa.json (ex.:
    disciplinas de pós-graduação), usando os metadados já presentes no
    próprio registro do docente. Sem isso, boa parte dos idSigaa referenciados
    nos perfis ficaria sem nome/ementa disponível em nenhum lugar."""
    catalogo: dict[str, dict] = {}

    for componente in componentes_payload.get("componentes", []):
        id_sigaa = componente.get("idSigaa")
        if not id_sigaa:
            continue
        catalogo[id_sigaa] = {
            "idSigaa": id_sigaa,
            "codigo": componente.get("codigo"),
            "nome": componente.get("nome"),
            "cargaHoraria": componente.get("cargaHoraria"),
            "ementa": componente.get("ementa"),
        }

    for docente in docentes_payload.get("docentes", []):
        for disciplina in docente.get("disciplinasMinistradas", []):
            id_sigaa = disciplina.get("idSigaa")
            if not id_sigaa or id_sigaa in catalogo:
                continue
            catalogo[id_sigaa] = {
                "idSigaa": id_sigaa,
                "codigo": disciplina.get("codigo"),
                "nome": disciplina.get("nome"),
                "cargaHoraria": disciplina.get("cargaHoraria"),
                "ementa": None,
            }

    return sorted(catalogo.values(), key=lambda c: c["idSigaa"])


def transformar_projetos_pesquisa(projetos: list[dict] | None) -> list[dict]:
    """Projetos de pesquisa do SIGAA: mantém só nome e área de conhecimento."""
    resultado: list[dict] = []
    vistos: set[str] = set()

    for projeto in projetos or []:
        titulo = normalizar_texto(projeto.get("titulo"))
        if not titulo:
            continue

        chave = titulo.lower()
        if chave in vistos:
            continue
        vistos.add(chave)

        resultado.append(
            {
                "id": gerar_id("pesquisa_sigaa", titulo, None),
                "tipo": "pesquisa_sigaa",
                "titulo": titulo,
                "areaConhecimento": normalizar_texto(projeto.get("areaConhecimento")) or None,
            }
        )

    return resultado


def eh_categoria_extensao(categoria: str) -> bool:
    return "extens" in categoria.lower()


def limpar_producao_docente(producao_intelectual: list[dict] | None) -> list[dict]:
    """Remove atividades de extensão, filtra a partir de 2016 (quando houver
    data disponível) e usa IA para extrair só o título de cada produção,
    descartando nomes de alunos e demais participantes."""
    resultado: list[dict] = []
    vistos: set[str] = set()

    for bloco in producao_intelectual or []:
        categoria = normalizar_texto(bloco.get("categoria"))
        itens = bloco.get("itens") or []
        if not categoria or not itens or eh_categoria_extensao(categoria):
            continue

        for extraido in extrair_titulos(itens):
            titulo = normalizar_texto(extraido.get("titulo"))
            if not titulo:
                continue

            ano = extraido.get("ano")
            if ano is not None and ano < PRODUCAO_ANO_MINIMO:
                continue

            id_producao = gerar_id("producao_docente", titulo, ano)
            if id_producao in vistos:
                continue
            vistos.add(id_producao)

            resultado.append(
                {
                    "id": id_producao,
                    "categoria": categoria,
                    "titulo": titulo,
                    "ano": ano,
                }
            )

    resultado.sort(key=lambda p: (p.get("ano") or 0, p["titulo"]), reverse=True)
    return resultado


def montar_perfil_sigaa(docente_bruto: dict) -> dict:
    perfil = limpar_perfil_sigaa(docente_bruto)
    return {
        "siape": docente_bruto.get("siape"),
        "descricaoPessoal": perfil["descricaoPessoal"],
        "formacaoAcademicaProfissional": perfil["formacaoAcademicaProfissional"],
        "areasInteresse": perfil["areasInteresse"],
        "disciplinasSigaa": normalizar_disciplinas(docente_bruto.get("disciplinasMinistradas", [])),
        "projetosSigaa": transformar_projetos_pesquisa(docente_bruto.get("projetosPesquisa")),
        "producaoDocente": limpar_producao_docente(docente_bruto.get("producaoIntelectual")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Limpa os perfis SIGAA (sem unificar com o Lattes) na camada Silver."
    )
    parser.add_argument("--docentes-sigaa", default=DEFAULT_DOCENTES_SIGAA)
    parser.add_argument("--componentes-sigaa", default=DEFAULT_COMPONENTES_SIGAA)
    parser.add_argument("--saida-perfis", default=DEFAULT_SAIDA_PERFIS)
    parser.add_argument("--saida-componentes", default=DEFAULT_SAIDA_COMPONENTES)
    args = parser.parse_args()

    docentes_sigaa_payload = ler_json_bronze(args.docentes_sigaa)
    componentes_payload = ler_json_bronze(args.componentes_sigaa)

    catalogo_componentes = construir_catalogo_disciplinas(componentes_payload, docentes_sigaa_payload)
    salvar_parquet_silver(args.saida_componentes, catalogo_componentes)

    perfis = [
        montar_perfil_sigaa(docente)
        for docente in docentes_sigaa_payload.get("docentes", [])
        if docente.get("siape")
    ]
    salvar_parquet_silver(args.saida_perfis, perfis)

    com_producao = sum(1 for p in perfis if p["producaoDocente"])
    print(f"Perfis SIGAA limpos: {len(perfis)} ({com_producao} com produção docente pós-{PRODUCAO_ANO_MINIMO}).")
    print(f"Componentes curriculares catalogados: {len(catalogo_componentes)}.")
    print(f"Parquet salvo em: silver/{args.saida_perfis}")


if __name__ == "__main__":
    main()
