#!/usr/bin/env python3
"""Limpa e normaliza os currículos Lattes na camada Silver (sem unir com o SIGAA).

Lê cada currículo bruto baixado pelo scriptLattes (Bronze) e produz um perfil
podado, focado em texto/semântica para embeddings (bge-m3): resumo,
competências, títulos de produções/projetos/orientações — sem autores,
veículo, DOI ou papel do professor no projeto.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bronze.minio_storage import ler_json_bronze, listar_chaves_bronze, salvar_parquet_silver  # noqa: E402

DEFAULT_LATTES_PREFIXO = "raw/lattes/json"
DEFAULT_SAIDA = "perfil_lattes_limpo.parquet"

ANO_LIMITE = datetime.now().year - 10

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

        trecho = descricao[match.end():]
        trecho = re.split(r"\.\s*Grande [áa]rea", trecho, maxsplit=1, flags=re.IGNORECASE)[0]
        trecho = re.split(r"\.\s*Setores de atividade", trecho, maxsplit=1, flags=re.IGNORECASE)[0]
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
    return [normalizar_texto(linha.get("nome")) for linha in linhas if normalizar_texto(linha.get("nome"))]


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


def parse_descricao_projeto(descricao: list[str] | str | None) -> tuple[str, str | None]:
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
    texto = re.sub(r"\s*Número de orientações:.*$", "", texto, flags=re.IGNORECASE).strip()

    return texto, situacao


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


def limpar_perfil_lattes(id_lattes: str, dados_bronze: dict) -> dict:
    """Perfil Lattes podado, focado em texto/semântica para embeddings."""
    info = dados_bronze.get("informacoes_pessoais") or {}

    projetos = transformar_projetos(dados_bronze.get("projetos_pesquisa"), "pesquisa")
    projetos.extend(transformar_projetos(dados_bronze.get("projetos_extensao"), "extensao"))
    projetos.extend(transformar_projetos(dados_bronze.get("projetos_desenvolvimento"), "desenvolvimento"))

    return {
        "idLattes": id_lattes,
        "resumo": limpar_resumo(info.get("texto_resumo")) or None,
        "competencias": {
            "areas": transformar_areas(dados_bronze.get("areas_de_atuacao") or []),
            "linhas_pesquisa": transformar_linhas(dados_bronze.get("linhas_de_pesquisa") or []),
            "palavras_chave": extrair_palavras_chave(dados_bronze.get("formacao_academica") or []),
        },
        "producoes": transformar_producoes(dados_bronze.get("producao_bibliografica")),
        "projetos": projetos,
        "orientacoes": transformar_orientacoes(dados_bronze.get("orientacoes")),
    }


def listar_ids_lattes(prefixo: str) -> list[str]:
    chaves = listar_chaves_bronze(f"{prefixo}/")
    ids = []
    for chave in chaves:
        nome_arquivo = chave.rsplit("/", 1)[-1]
        id_lattes = nome_arquivo.removesuffix(".json")
        if id_lattes:
            ids.append(id_lattes)
    return sorted(ids)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Limpa os currículos Lattes (sem unificar com o SIGAA) na camada Silver."
    )
    parser.add_argument("--lattes-prefixo", default=DEFAULT_LATTES_PREFIXO)
    parser.add_argument("--saida", default=DEFAULT_SAIDA)
    args = parser.parse_args()

    ids_lattes = listar_ids_lattes(args.lattes_prefixo)
    if not ids_lattes:
        raise RuntimeError(f"Nenhum currículo Lattes encontrado em bronze/{args.lattes_prefixo}/.")

    perfis = []
    for id_lattes in ids_lattes:
        dados_bronze = ler_json_bronze(f"{args.lattes_prefixo}/{id_lattes}.json")
        perfis.append(limpar_perfil_lattes(id_lattes, dados_bronze))

    salvar_parquet_silver(args.saida, perfis)

    com_resumo = sum(1 for p in perfis if p["resumo"])
    print(f"Perfis Lattes limpos: {len(perfis)} ({com_resumo} com resumo).")
    print(f"Parquet salvo em: silver/{args.saida}")


if __name__ == "__main__":
    main()
