#!/usr/bin/env python3
"""Limpa, unifica e normaliza os perfis SIGAA + Lattes na camada Silver.

Lê o roster de identidade (Silver), os JSONs brutos do SIGAA e do Lattes e o
catálogo de trabalhos de IC/periódicos (Bronze) e produz um perfil único por
professor, pronto para gerar embeddings (bge-m3): campos textuais essenciais
(resumo, competências, títulos de produções/projetos/orientações), disciplinas
reduzidas a IDs do catálogo de componentes, e trabalhos de IC reduzidos a IDs
de um catálogo à parte.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

sys.path.insert(0, str(ROOT_DIR / "silver" / "01_merge"))

from bronze.minio_storage import (
    ler_json_bronze,  # noqa: E402
    ler_parquet_silver,
    listar_chaves_bronze,
    salvar_parquet_silver,
)
from merge_professores import chave_nome, similaridade_nomes  # noqa: E402

DEFAULT_ROSTER = "professores_unificados.parquet"
DEFAULT_DOCENTES_SIGAA = "raw/sigaa/docentes_sigaa.json"
DEFAULT_LATTES_PREFIXO = "raw/lattes/json"
DEFAULT_TRABALHOS_IC = "raw/periodicos/trabalhos_ic_periodicos.json"
DEFAULT_COMPONENTES_SIGAA = "raw/sigaa/componentes_sigaa.json"
DEFAULT_SAIDA_PROFESSORES = "professores_unificados.parquet"
DEFAULT_SAIDA_TRABALHOS_IC = "trabalhos_ic_periodicos.parquet"
DEFAULT_SAIDA_COMPONENTES = "componentes_curriculares.parquet"

ANO_LIMITE = datetime.now().year - 10
LIMIAR_SIMILARIDADE_ORIENTADOR = 0.92

MAPEAMENTO_PRODUCAO = {
    "artigos_periodicos": "artigo_periodico",
    "livros_publicados": "livro",
    "capitulos_livros": "capitulo_livro",
    "trabalhos_completos_congressos": "trabalho_congresso",
    "resumos_expandidos": "resumo_expandido",
    "resumos_congressos": "resumo_congresso",
    "artigos_aceitos": "artigo_aceito",
    "textos_jornais": "texto_jornal",
    "outras_producoes": "outra_producao",
}

CATEGORIAS_ORIENTACAO = (
    "pos_doutorado",
    "doutorado",
    "mestrado",
    "especializacao",
    "tcc",
    "iniciacao_cientifica",
)

SUFIXO_RESUMO = "(Texto informado pelo autor)"


def normalizar_texto(texto: str | None) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip()


def limpar_resumo(texto: str | None) -> str:
    texto = normalizar_texto(texto)
    if texto.endswith(SUFIXO_RESUMO):
        texto = texto[: -len(SUFIXO_RESUMO)].strip()
    return texto.rstrip(".").strip()


def normalizar_ano(valor: str | int | None) -> int | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() == "atual":
        return datetime.now(timezone.utc).year
    if texto.isdigit():
        return int(texto)
    return None


def gerar_id(tipo: str, titulo: str, ano: int | None) -> str:
    base = f"{tipo}|{titulo}|{ano or ''}".lower()
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def extrair_palavras_chave(formacoes: list[dict]) -> list[str]:
    palavras: list[str] = []
    vistos: set[str] = set()

    for formacao in formacoes:
        descricao = formacao.get("descricao") or ""
        match = re.search(r"palavras?-chave:\s*", descricao, flags=re.IGNORECASE)
        if not match:
            continue

        trecho = descricao[match.end() :]
        trecho = re.split(
            r"\.\s*Grande [áa]rea", trecho, maxsplit=1, flags=re.IGNORECASE
        )[0]
        trecho = re.split(
            r"\.\s*Setores de atividade", trecho, maxsplit=1, flags=re.IGNORECASE
        )[0]
        trecho = trecho.split(".")[0]

        for palavra in re.split(r"[;/]", trecho):
            palavra = normalizar_texto(palavra)
            if not palavra:
                continue
            chave = palavra.lower()
            if chave not in vistos:
                vistos.add(chave)
                palavras.append(palavra)

    return palavras


def transformar_areas(areas: list[dict]) -> list[dict]:
    resultado = []
    for area in areas:
        item = {
            "grande_area": normalizar_texto(area.get("grande_area")),
            "area": normalizar_texto(area.get("area")),
            "subarea": normalizar_texto(area.get("subarea")),
        }
        especialidade = normalizar_texto(area.get("especialidade"))
        if especialidade:
            item["especialidade"] = especialidade
        if any(item.values()):
            resultado.append(item)
    return resultado


def transformar_linhas(linhas: list[dict]) -> list[str]:
    return [
        normalizar_texto(linha.get("nome"))
        for linha in linhas
        if normalizar_texto(linha.get("nome"))
    ]


def transformar_producoes(producao_bibliografica: dict | None) -> list[dict]:
    """Extrai só id/tipo/titulo/ano de cada produção (poda autores/veículo/DOI)."""
    if not producao_bibliografica:
        return []

    producoes: list[dict] = []
    vistos: set[str] = set()
    for chave_bronze, tipo_silver in MAPEAMENTO_PRODUCAO.items():
        for item in producao_bibliografica.get(chave_bronze, []) or []:
            titulo = normalizar_texto(item.get("titulo"))
            if not titulo:
                continue

            ano = normalizar_ano(item.get("ano"))
            if ano and ano < ANO_LIMITE:
                break

            id_producao = gerar_id(tipo_silver, titulo, ano)
            if id_producao in vistos:
                continue
            vistos.add(id_producao)

            producoes.append(
                {
                    "id": id_producao,
                    "tipo": tipo_silver,
                    "titulo": titulo,
                    "ano": ano,
                }
            )

    producoes.sort(key=lambda p: (p.get("ano") or 0, p["titulo"]), reverse=True)
    return producoes


def transformar_projetos(projetos: list[dict], tipo_projeto: str) -> list[dict]:
    """Extrai id/tipo/nome/anos/situacao/descricao (poda o campo papel)."""
    resultado: list[dict] = []
    vistos: set[str] = set()

    for projeto in projetos or []:
        nome = normalizar_texto(projeto.get("nome"))
        if not nome:
            continue

        ano_inicio = normalizar_ano(projeto.get("ano_inicio"))
        if ano_inicio and ano_inicio < ANO_LIMITE:
            break

        chave = f"{tipo_projeto}|{nome.lower()}|{ano_inicio or ''}"
        if chave in vistos:
            continue
        vistos.add(chave)

        descricao, situacao = parse_descricao_projeto(projeto.get("descricao"))

        item = {
            "id": gerar_id(tipo_projeto, nome, ano_inicio),
            "tipo": tipo_projeto,
            "nome": nome,
            "ano_inicio": ano_inicio,
            "ano_conclusao": normalizar_ano(projeto.get("ano_conclusao")),
            "situacao": situacao,
            "descricao": descricao or None,
        }
        resultado.append({k: v for k, v in item.items() if v is not None})

    return resultado


def parse_descricao_projeto(
    descricao: list[str] | str | None,
) -> tuple[str, str | None]:
    if not descricao:
        return "", None

    if isinstance(descricao, list):
        texto = " ".join(normalizar_texto(item) for item in descricao if item)
    else:
        texto = normalizar_texto(descricao)

    texto = re.sub(r"^Descrição:\s*", "", texto, flags=re.IGNORECASE)

    situacao = None
    match = re.search(r"Situação:\s*([^.;]+)", texto, flags=re.IGNORECASE)
    if match:
        situacao_bruta = match.group(1).strip().lower()
        if "andamento" in situacao_bruta:
            situacao = "em_andamento"
        elif "conclu" in situacao_bruta:
            situacao = "concluido"
        texto = texto[: match.start()].strip()

    texto = re.sub(r"\s*Integrantes:.*$", "", texto, flags=re.IGNORECASE).strip()
    texto = re.sub(r"\s*Alunos envolvidos:.*$", "", texto, flags=re.IGNORECASE).strip()
    texto = re.sub(r"\s*Financiador(?:es)?:.*$", "", texto, flags=re.IGNORECASE).strip()
    texto = re.sub(
        r"\s*Número de orientações:.*$", "", texto, flags=re.IGNORECASE
    ).strip()

    return texto, situacao


def transformar_orientacoes(orientacoes: dict | None) -> list[dict]:
    if not orientacoes:
        return []

    resultado: list[dict] = []
    vistos: set[str] = set()
    for status in ("em_andamento", "concluidas"):
        bloco = orientacoes.get(status) or {}
        for categoria in CATEGORIAS_ORIENTACAO:
            for orientacao in bloco.get(categoria, []) or []:
                titulo = normalizar_texto(orientacao.get("titulo"))
                if not titulo or titulo == "Estágio Supervisionado":
                    continue

                ano_inicio = normalizar_ano(orientacao.get("ano_inicio"))
                if ano_inicio and ano_inicio < ANO_LIMITE:
                    continue

                # Mesmo título/ano pode ter vários orientandos (trabalho em grupo);
                # como o orientando não faz parte do perfil, mantém só uma entrada.
                id_orientacao = gerar_id(categoria, titulo, ano_inicio)
                if id_orientacao in vistos:
                    continue
                vistos.add(id_orientacao)

                item = {
                    "id": id_orientacao,
                    "tipo": categoria,
                    "titulo": titulo,
                    "ano_inicio": ano_inicio,
                }
                resultado.append({k: v for k, v in item.items() if v is not None})

    resultado.sort(key=lambda o: (o.get("ano_inicio") or 0, o["titulo"]), reverse=True)
    return resultado


def limpar_perfil_lattes(dados_bronze: dict) -> dict:
    """Perfil Lattes podado, focado em texto/semântica para embeddings."""
    info = dados_bronze.get("informacoes_pessoais") or {}

    projetos = transformar_projetos(dados_bronze.get("projetos_pesquisa"), "pesquisa")
    projetos.extend(
        transformar_projetos(dados_bronze.get("projetos_extensao"), "extensao")
    )
    projetos.extend(
        transformar_projetos(
            dados_bronze.get("projetos_desenvolvimento"), "desenvolvimento"
        )
    )

    return {
        "resumo": limpar_resumo(info.get("texto_resumo")) or None,
        "competencias": {
            "areas": transformar_areas(dados_bronze.get("areas_de_atuacao") or []),
            "linhas_pesquisa": transformar_linhas(
                dados_bronze.get("linhas_de_pesquisa") or []
            ),
            "palavras_chave": extrair_palavras_chave(
                dados_bronze.get("formacao_academica") or []
            ),
        },
        "producoes": transformar_producoes(dados_bronze.get("producao_bibliografica")),
        "projetos": projetos,
        "orientacoes": transformar_orientacoes(dados_bronze.get("orientacoes")),
    }


PLACEHOLDERS_AREA_INTERESSE = {
    "não informadas",
    "nao informadas",
    "não informada",
    "nao informada",
}


def limpar_perfil_sigaa(docente_bruto: dict) -> dict:
    """Perfil SIGAA podado: só o que agrega semântica (descarta contatos/URLs)."""
    perfil = docente_bruto.get("perfil") or {}
    areas_interesse = [
        normalizar_texto(a)
        for a in perfil.get("areasInteresse", [])
        if normalizar_texto(a)
        and normalizar_texto(a).lower() not in PLACEHOLDERS_AREA_INTERESSE
    ]
    return {
        "descricaoPessoal": normalizar_texto(perfil.get("descricaoPessoal")) or None,
        "formacaoAcademicaProfissional": normalizar_texto(
            perfil.get("formacaoAcademicaProfissional")
        )
        or None,
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


def extrair_orientador(autores_texto: str) -> str:
    """Por convenção, o último autor listado é o orientador do trabalho."""
    partes = [p.strip() for p in autores_texto.split(",") if p.strip()]
    return partes[-1] if partes else ""


def indexar_lattes_disponiveis() -> set[str]:
    chaves = listar_chaves_bronze(f"{DEFAULT_LATTES_PREFIXO}/")
    ids = set()
    for chave in chaves:
        nome_arquivo = chave.rsplit("/", 1)[-1]
        id_lattes = nome_arquivo.removesuffix(".json")
        if id_lattes:
            ids.add(id_lattes)
    return ids


def processar_trabalhos_ic(
    chave_trabalhos: str,
    roster: list[dict],
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Casa cada trabalho de IC com um professor do roster pelo orientador.

    Retorna (mapa siape -> lista de ids de trabalhos, catálogo de trabalhos).
    """
    trabalhos = ler_json_bronze(chave_trabalhos)
    roster_por_chave = [(chave_nome(p["nome"]), p) for p in roster if p.get("nome")]

    trabalhos_por_siape: dict[str, list[dict]] = {}
    catalogo: list[dict] = []

    for trabalho in trabalhos:
        autores = trabalho.get("autores") or ""
        orientador = extrair_orientador(autores)
        if not orientador:
            continue

        melhor_professor = None
        melhor_score = 0.0
        for _, professor in roster_por_chave:
            score = similaridade_nomes(orientador, professor["nome"])
            if score >= LIMIAR_SIMILARIDADE_ORIENTADOR and score > melhor_score:
                melhor_score = score
                melhor_professor = professor

        if melhor_professor is None:
            continue

        titulo = normalizar_texto(trabalho.get("titulo"))
        ano = normalizar_ano(trabalho.get("ano"))
        id_trabalho = gerar_id("trabalho_ic", titulo, ano)

        catalogo.append(
            {
                "id": id_trabalho,
                "titulo": titulo,
                "autores": normalizar_texto(autores),
                "resumo": normalizar_texto(trabalho.get("resumo")) or None,
                "palavrasChaves": trabalho.get("palavrasChaves", []),
                "ano": ano,
            }
        )

        siape = melhor_professor.get("siape")
        if siape:
            trabalhos_por_siape.setdefault(siape, []).append(id_trabalho)

    return trabalhos_por_siape, catalogo


def montar_professor(
    identidade: dict,
    docentes_sigaa_por_siape: dict[str, dict],
    lattes_disponiveis: set[str],
    trabalhos_por_siape: dict[str, list[str]],
) -> dict:
    nome = identidade.get("nome")
    id_lattes = identidade.get("idLattes")
    siape = identidade.get("siape")

    docente_sigaa = docentes_sigaa_por_siape.get(siape, {}) if siape else {}
    perfil_sigaa = limpar_perfil_sigaa(docente_sigaa)
    disciplinas = normalizar_disciplinas(
        docente_sigaa.get("disciplinasMinistradas", [])
    )

    perfil_lattes: dict[str, Any] = {
        "resumo": None,
        "competencias": {"areas": [], "linhas_pesquisa": [], "palavras_chave": []},
        "producoes": [],
        "projetos": [],
        "orientacoes": [],
    }
    if id_lattes and id_lattes in lattes_disponiveis:
        dados_lattes = ler_json_bronze(f"{DEFAULT_LATTES_PREFIXO}/{id_lattes}.json")
        perfil_lattes = limpar_perfil_lattes(dados_lattes)
    elif id_lattes:
        print(f"AVISO: sem JSON Lattes para {nome} (idLattes={id_lattes}).")

    resumo = perfil_lattes["resumo"] or perfil_sigaa["descricaoPessoal"]

    return {
        "nome": nome,
        "idLattes": id_lattes,
        "siape": siape,
        "resumo": resumo,
        "formacaoAcademicaProfissional": perfil_sigaa["formacaoAcademicaProfissional"],
        "areasInteresse": perfil_sigaa["areasInteresse"],
        "competencias": perfil_lattes["competencias"],
        "producoes": perfil_lattes["producoes"],
        "projetos": perfil_lattes["projetos"],
        "orientacoes": perfil_lattes["orientacoes"],
        "disciplinasSigaa": disciplinas,
        "trabalhosIniciacaoCientifica": (
            trabalhos_por_siape.get(siape, []) if siape else []
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Limpa, unifica e normaliza os perfis SIGAA + Lattes na Silver."
    )
    parser.add_argument("--roster", default=DEFAULT_ROSTER)
    parser.add_argument("--docentes-sigaa", default=DEFAULT_DOCENTES_SIGAA)
    parser.add_argument("--componentes-sigaa", default=DEFAULT_COMPONENTES_SIGAA)
    parser.add_argument("--trabalhos-ic", default=DEFAULT_TRABALHOS_IC)
    parser.add_argument("--saida-professores", default=DEFAULT_SAIDA_PROFESSORES)
    parser.add_argument("--saida-trabalhos-ic", default=DEFAULT_SAIDA_TRABALHOS_IC)
    parser.add_argument("--saida-componentes", default=DEFAULT_SAIDA_COMPONENTES)
    args = parser.parse_args()

    roster = ler_parquet_silver(args.roster)
    docentes_sigaa_payload = ler_json_bronze(args.docentes_sigaa)
    docentes_sigaa_por_siape = {
        d["siape"]: d
        for d in docentes_sigaa_payload.get("docentes", [])
        if d.get("siape")
    }
    componentes_payload = ler_json_bronze(args.componentes_sigaa)
    lattes_disponiveis = indexar_lattes_disponiveis()

    catalogo_componentes = construir_catalogo_disciplinas(
        componentes_payload, docentes_sigaa_payload
    )
    salvar_parquet_silver(args.saida_componentes, catalogo_componentes)

    trabalhos_por_siape, catalogo_trabalhos_ic = processar_trabalhos_ic(
        args.trabalhos_ic, roster
    )
    if catalogo_trabalhos_ic:
        salvar_parquet_silver(args.saida_trabalhos_ic, catalogo_trabalhos_ic)

    professores = [
        montar_professor(
            identidade,
            docentes_sigaa_por_siape,
            lattes_disponiveis,
            trabalhos_por_siape,
        )
        for identidade in roster
    ]
    salvar_parquet_silver(args.saida_professores, professores)

    com_resumo = sum(1 for p in professores if p["resumo"])
    com_ic = sum(1 for p in professores if p["trabalhosIniciacaoCientifica"])
    print(f"Perfis unificados: {len(professores)} ({com_resumo} com resumo).")
    print(
        f"Trabalhos de IC catalogados: {len(catalogo_trabalhos_ic)} ({com_ic} professores com IC vinculada)."
    )
    print(f"Componentes curriculares catalogados: {len(catalogo_componentes)}.")
    print(f"Parquet salvo em: silver/{args.saida_professores}")


if __name__ == "__main__":
    main()
