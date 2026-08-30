#!/usr/bin/env python3
"""Transforma JSONs do scriptLattes (Bronze) em perfis limpos (Silver)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENTRADA = ROOT_DIR / "data" / "bronze" / "lattes" / "json"
DEFAULT_SAIDA = ROOT_DIR / "data" / "silver" / "docentes"

ano_limite = datetime.now().year - 10

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
    "iniciacao_cientifica"
)

SUFIXO_RESUMO = "(Texto informado pelo autor)"


def normalizar_texto(texto: str | None) -> str:
    if not texto:
        return ""
    texto = re.sub(r"\s+", " ", str(texto)).strip()
    return texto


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


def normalizar_data_cv(valor: str | None) -> str | None:
    if not valor:
        return None
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", valor.strip())
    if not match:
        return valor
    dia, mes, ano = match.groups()
    return f"{ano}-{mes}-{dia}"


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


def extrair_unidade(endereco: str | None) -> str | None:
    if not endereco:
        return None
    if re.search(r"IESTI|Instituto de Engenharia de Sistemas", endereco, re.I):
        return "IESTI"
    return None


def extrair_instituicao_atual(atuacoes: list[dict]) -> dict[str, str | None]:
    candidatos = []
    for atuacao in atuacoes:
        ano_fim = str(atuacao.get("ano_fim") or "").strip().lower()
        periodo = str(atuacao.get("periodo") or "").lower()
        if ano_fim != "atual" and "atual" not in periodo:
            continue

        enquadramento = normalizar_texto(atuacao.get("enquadramento"))
        vinculo = normalizar_texto(atuacao.get("vinculo"))
        if enquadramento and "professor" not in enquadramento.lower():
            if "servidor" not in vinculo.lower():
                continue

        candidatos.append(atuacao)

    if not candidatos:
        return {
            "instituicao_atual": None,
            "instituicao_sigla": None,
            "cargo": None,
            "vinculo": None,
        }

    preferida = next(
        (a for a in candidatos if str(a.get("instituicao_sigla") or "").upper() == "UNIFEI"),
        candidatos[0],
    )

    return {
        "instituicao_atual": normalizar_texto(preferida.get("instituicao_nome")),
        "instituicao_sigla": normalizar_texto(preferida.get("instituicao_sigla")),
        "cargo": normalizar_texto(preferida.get("enquadramento") or preferida.get("cargo_funcao")),
        "vinculo": normalizar_texto(preferida.get("vinculo")),
    }


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


def papel_no_projeto(integrantes: list[dict], nome_docente: str) -> str | None:
    nome_docente = nome_docente.lower()
    for integrante in integrantes:
        nome = str(integrante.get("nome") or "").lower()
        if not nome or nome not in nome_docente and nome_docente not in nome:
            partes = nome_docente.split()
            if not partes or partes[0] not in nome:
                continue
        papel = str(integrante.get("papel") or "").lower()
        if "coorden" in papel:
            return "coordenador"
        if "integr" in papel:
            return "integrante"
        return normalizar_texto(integrante.get("papel")) or None
    return None


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
    resultado = []
    for linha in linhas:
        nome = normalizar_texto(linha.get("nome"))
        if nome:
            resultado.append(nome)
    return resultado


def transformar_producoes(producao_bibliografica: dict | None) -> list[dict]:
    if not producao_bibliografica:
        return []

    producoes: list[dict] = []
    for chave_bronze, tipo_silver in MAPEAMENTO_PRODUCAO.items():
        for item in producao_bibliografica.get(chave_bronze, []) or []:
            titulo = normalizar_texto(item.get("titulo"))
            if not titulo:
                continue

            ano = normalizar_ano(item.get("ano"))
            if ano and ano < ano_limite:
                break
            
            veiculo = normalizar_texto(
                item.get("revista") or item.get("evento") or item.get("titulo_livro")
            )

            producao = {
                "id": gerar_id(tipo_silver, titulo, ano),
                "tipo": tipo_silver,
                "titulo": titulo,
                "ano": ano,
                #"veiculo": veiculo or None,
                "doi": normalizar_texto(item.get("doi")) or None,
            }
            producoes.append({k: v for k, v in producao.items() if v is not None})

    producoes.sort(key=lambda p: (p.get("ano") or 0, p["titulo"]), reverse=True)
    return producoes


def transformar_projetos(
    projetos: list[dict],
    tipo_projeto: str,
    nome_docente: str,
) -> list[dict]:
    resultado: list[dict] = []
    vistos: set[str] = set()

    for projeto in projetos or []:
        nome = normalizar_texto(projeto.get("nome"))
        if not nome:
            continue

        ano_inicio = normalizar_ano(projeto.get("ano_inicio"))
        
        if ano_inicio and ano_inicio < ano_limite:
            break
        
        chave = f"{tipo_projeto}|{nome.lower()}|{ano_inicio or ''}"
        if chave in vistos:
            continue
        vistos.add(chave)

        descricao, situacao = parse_descricao_projeto(projeto.get("descricao"))
        integrantes = projeto.get("integrantes") or []

        item = {
            "id": gerar_id(tipo_projeto, nome, ano_inicio),
            "tipo": tipo_projeto,
            "nome": nome,
            "ano_inicio": ano_inicio,
            "ano_conclusao": normalizar_ano(projeto.get("ano_conclusao")),
            "situacao": situacao,
            "descricao": descricao or None,
            "papel": papel_no_projeto(integrantes, nome_docente),
        }
        resultado.append({k: v for k, v in item.items() if v is not None})

    return resultado


def transformar_orientacoes(orientacoes: dict | None) -> list[dict]:
    if not orientacoes:
        return []

    resultado: list[dict] = []
    for status in ("em_andamento", "concluidas"):
        bloco = orientacoes.get(status) or {}
        status_silver = "em_andamento" if status == "em_andamento" else "concluida"

        for categoria in CATEGORIAS_ORIENTACAO:
            for orientacao in bloco.get(categoria, []) or []:
                titulo = normalizar_texto(orientacao.get("titulo"))
                if not titulo:
                    continue
                
                if titulo == "Estágio Supervisionado":
                    break

                ano_inicio = normalizar_ano(orientacao.get("ano_inicio"))
                ano_conclusao = normalizar_ano(orientacao.get("ano_conclusao"))
                
                if ano_inicio and ano_inicio < ano_limite:
                    break
                
                item = {
                    "id": gerar_id(categoria, titulo, ano_inicio),
                    "tipo": categoria,
                    "titulo": titulo,
                    "ano_inicio": ano_inicio,
                }
                resultado.append({k: v for k, v in item.items() if v is not None})

    resultado.sort(
        key=lambda o: (o.get("ano_inicio") or 0, o["titulo"]),
        reverse=True,
    )
    return resultado


def transformar_lattes(dados_bronze: dict, arquivo_bronze: Path) -> dict:
    info = dados_bronze.get("informacoes_pessoais") or {}
    nome = normalizar_texto(info.get("nome_completo"))
    id_lattes = normalizar_texto(info.get("id_lattes"))

    instituicao = extrair_instituicao_atual(dados_bronze.get("atuacao_profissional") or [])

    projetos = transformar_projetos(
        dados_bronze.get("projetos_pesquisa"),
        "pesquisa",
        nome,
    )
    projetos.extend(
        transformar_projetos(dados_bronze.get("projetos_extensao"), "extensao", nome)
    )
    projetos.extend(
        transformar_projetos(
            dados_bronze.get("projetos_desenvolvimento"),
            "desenvolvimento",
            nome,
        )
    )

    return {
        "docente": {
            "id_lattes": id_lattes,
            "nome": nome,
            "resumo": limpar_resumo(info.get("texto_resumo")) or None,
            "instituicao_atual": instituicao["instituicao_atual"],
            "instituicao_sigla": instituicao["instituicao_sigla"],
            "cargo": instituicao["cargo"],
            "vinculo": instituicao["vinculo"],
            "unidade": extrair_unidade(info.get("endereco_profissional")),
            "atualizacao_cv": normalizar_data_cv(info.get("atualizacao_cv")),
        },
        "competencias": {
            "areas": transformar_areas(dados_bronze.get("areas_de_atuacao") or []),
            "linhas_pesquisa": transformar_linhas(dados_bronze.get("linhas_de_pesquisa") or []),
            "palavras_chave": extrair_palavras_chave(dados_bronze.get("formacao_academica") or []),
        },
        "producoes": transformar_producoes(dados_bronze.get("producao_bibliografica")),
        "projetos": projetos,
        "orientacoes": transformar_orientacoes(dados_bronze.get("orientacoes")),
        "linhagem": {
            "fonte": "lattes",
            "arquivo_bronze": arquivo_bronze.name,
            "processado_em": datetime.now(timezone.utc).isoformat(),
        },
    }


def limpar_docente(docente: dict) -> dict:
    docente_limpo = {k: v for k, v in docente["docente"].items() if v is not None}
    return {
        "docente": docente_limpo,
        "competencias": docente["competencias"],
        "producoes": docente["producoes"],
        "projetos": docente["projetos"],
        "orientacoes": docente["orientacoes"],
        "linhagem": docente["linhagem"],
    }


def processar_arquivo(arquivo_entrada: Path, diretorio_saida: Path) -> dict:
    dados_bronze = json.loads(arquivo_entrada.read_text(encoding="utf-8"))
    docente_silver = limpar_docente(transformar_lattes(dados_bronze, arquivo_entrada))

    id_lattes = docente_silver["docente"]["id_lattes"]
    if not id_lattes:
        raise ValueError(f"ID Lattes ausente em {arquivo_entrada}")

    diretorio_saida.mkdir(parents=True, exist_ok=True)
    arquivo_saida = diretorio_saida / f"{id_lattes}.json"
    with arquivo_saida.open("w", encoding="utf-8") as arquivo:
        json.dump(docente_silver, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")

    return {
        "id_lattes": id_lattes,
        "nome": docente_silver["docente"]["nome"],
        "producoes": len(docente_silver["producoes"]),
        "projetos": len(docente_silver["projetos"]),
        "orientacoes": len(docente_silver["orientacoes"]),
        "palavras_chave": len(docente_silver["competencias"]["palavras_chave"]),
        "arquivo_saida": str(arquivo_saida),
    }


def gerar_relatorio(resumos: list[dict], diretorio_saida: Path) -> str:
    total_producoes = sum(r["producoes"] for r in resumos)
    total_projetos = sum(r["projetos"] for r in resumos)
    total_orientacoes = sum(r["orientacoes"] for r in resumos)

    linhas = [
        "RELATÓRIO SILVER — TRANSFORMAÇÃO LATTES",
        "=" * 50,
        f"Docentes processados: {len(resumos)}",
        f"Total de produções: {total_producoes}",
        f"Total de projetos: {total_projetos}",
        f"Total de orientações: {total_orientacoes}",
        "",
        "Detalhes por docente:",
    ]

    for resumo in sorted(resumos, key=lambda r: r["nome"]):
        linhas.append(
            f"  - {resumo['nome']} ({resumo['id_lattes']}): "
            f"{resumo['producoes']} produções, {resumo['projetos']} projetos, "
            f"{resumo['orientacoes']} orientações, "
            f"{resumo['palavras_chave']} palavras-chave"
        )

    return "\n".join(linhas) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transforma todos os JSONs Lattes da Bronze em perfis Silver."
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        default=DEFAULT_ENTRADA,
        help="Diretório com JSONs do scriptLattes.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=DEFAULT_SAIDA,
        help="Diretório de saída dos JSONs Silver.",
    )
    args = parser.parse_args()

    arquivos = sorted(args.entrada.glob("*.json"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum JSON encontrado em {args.entrada}")

    resumos = []
    for arquivo in arquivos:
        resumo = processar_arquivo(arquivo, args.saida)
        resumos.append(resumo)
        print(f"OK {resumo['nome']} -> {resumo['arquivo_saida']}")

    relatorio = gerar_relatorio(resumos, args.saida)
    relatorio_path = args.saida.parent / "relatorio_transformacao.txt"
    relatorio_path.write_text(relatorio, encoding="utf-8")

    print()
    print(relatorio)
    print(f"Relatório salvo em: {relatorio_path}")


if __name__ == "__main__":
    main()
