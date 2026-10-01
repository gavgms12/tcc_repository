#!/usr/bin/env python3
"""Unifica os perfis SIGAA + Lattes já limpos (Silver) num perfil por professor.

Lê `perfis_sigaa_limpos.parquet` e `perfis_lattes_limpos.parquet` da Silver e
os funde num único documento por professor: resolve `disciplinasSigaa` (IDs)
e `trabalhosIniciacaoCientifica` (IDs) para o texto real dos catálogos
(`componentes_curriculares[_externos].parquet`, `trabalhos_ic_periodicos.parquet`),
deduplica tópicos/áreas de interesse que aparecem nas duas fontes e evita
repetir o mesmo resumo duas vezes. Cada perfil final é salvo como um JSON
próprio no bucket Gold, sob o prefixo `perfil_professores/`.

Ao final, valida se cada perfil resultante tem conteúdo textual suficiente
para gerar um embedding útil no BGE-M3 (perfis "vazios" — sem resumo, sem
tópicos, sem nenhuma produção/disciplina resolvida — são reportados, não
descartados silenciosamente).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from storage.minio_storage import ler_parquet_silver, salvar_json_gold

DEFAULT_PERFIS_SIGAA = "perfis_sigaa_limpos.parquet"
DEFAULT_PERFIS_LATTES = "perfis_lattes_limpos.parquet"
DEFAULT_COMPONENTES_IESTI = "componentes_curriculares.parquet"
DEFAULT_COMPONENTES_EXTERNOS = "componentes_curriculares_externos.parquet"
DEFAULT_TRABALHOS_IC = "trabalhos_ic_periodicos.parquet"
DEFAULT_PREFIXO_SAIDA = "perfil_professores"


def normalizar_texto(texto: str | None) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip()


def identificador_professor(perfil: dict) -> str:
    """Nome de arquivo estável: idLattes quando existe, senão siape."""
    return str(perfil.get("idLattes") or perfil.get("siape"))


def construir_catalogo(*parquets: list[dict], chave_id: str) -> dict[str, dict]:
    """Indexa uma lista de registros (de um ou mais catálogos) pelo campo id."""
    catalogo: dict[str, dict] = {}
    for registros in parquets:
        for registro in registros:
            id_registro = registro.get(chave_id)
            if id_registro and id_registro not in catalogo:
                catalogo[id_registro] = registro
    return catalogo


def resolver_disciplinas(ids: list[str], catalogo: dict[str, dict]) -> list[dict]:
    """Troca os idSigaa por {codigo, nome, ementa} — o id sozinho não tem
    nenhum valor semântico para o modelo de embedding.

    Códigos diferentes às vezes compartilham o mesmo nome de disciplina (ex.:
    ofertas/currículos diferentes ao longo do tempo), mas com ementas
    distintas — descartar por nome perderia uma ementa real. Só remove quando
    nome E ementa são idênticos (duplicata de fato, ex.: o mesmo id aparecendo
    duas vezes na lista de origem)."""
    resolvidas: list[dict] = []
    vistas: set[tuple[str, str]] = set()
    ids_sem_correspondencia = []
    for id_sigaa in ids or []:
        info = catalogo.get(id_sigaa)
        if not info:
            ids_sem_correspondencia.append(id_sigaa)
            continue

        disciplina = {
            k: v for k, v in info.items() if k != "idSigaa" and v not in (None, "")
        }
        chave = (
            normalizar_texto(disciplina.get("nome")).lower(),
            normalizar_texto(disciplina.get("ementa")).lower(),
        )
        if chave in vistas:
            continue
        vistas.add(chave)
        resolvidas.append(disciplina)

    if ids_sem_correspondencia:
        print(
            f"  AVISO: {len(ids_sem_correspondencia)} idSigaa sem catálogo: "
            f"{', '.join(ids_sem_correspondencia)}"
        )
    return resolvidas


def resolver_trabalhos_ic(ids: list[str], catalogo: dict[str, dict]) -> list[dict]:
    """Troca os ids de trabalho de IC pelo texto real (título, resumo,
    palavras-chave) — mesmo racional de resolver_disciplinas."""
    resolvidos = []
    for id_trabalho in ids or []:
        info = catalogo.get(id_trabalho)
        if info:
            resolvidos.append({k: v for k, v in info.items() if k != "id"})
    return resolvidos


def unificar_topicos(*listas: list[str] | None, excluir: set[str] = frozenset()) -> list[str]:
    """Junta listas de tópicos/áreas de interesse vindas de fontes diferentes,
    removendo duplicatas (comparação case-insensitive) sem perder a ordem.

    Alguns itens de `areasInteresse` (SIGAA) vêm como uma única string com
    várias áreas separadas por vírgula (ex.: "Usabilidade, Equipamentos
    Médicos, Engenharia Biomédica") em vez de já estarem em itens separados;
    sem quebrar por vírgula aqui, esse texto composto nunca colide com os
    termos equivalentes que o Lattes já traz separados, e a duplicação passa
    despercebida. `excluir` permite remover termos que já aparecem em outro
    campo estruturado do perfil (ex.: área/subárea de `areasEspecializacao`).
    """
    vistos: set[str] = {termo.lower() for termo in excluir}
    resultado: list[str] = []
    for lista in listas:
        for item in lista or []:
            for pedaco in str(item or "").split(","):
                texto = normalizar_texto(pedaco)
                if not texto:
                    continue
                chave = texto.lower()
                if chave in vistos:
                    continue
                vistos.add(chave)
                resultado.append(texto)
    return resultado


def unificar_resumo(resumo_lattes: str | None, descricao_sigaa: str | None) -> str | None:
    """Combina o resumo do Lattes com a descrição pessoal do SIGAA sem
    repetir o texto quando as duas fontes dizem a mesma coisa."""
    resumo_lattes = normalizar_texto(resumo_lattes)
    descricao_sigaa = normalizar_texto(descricao_sigaa)

    if resumo_lattes and descricao_sigaa:
        if resumo_lattes.lower() == descricao_sigaa.lower():
            return resumo_lattes
        return f"{resumo_lattes}\n\n{descricao_sigaa}"
    return resumo_lattes or descricao_sigaa or None


def montar_perfil_unificado(
    sigaa: dict,
    lattes: dict | None,
    catalogo_disciplinas: dict[str, dict],
    catalogo_trabalhos: dict[str, dict],
) -> dict:
    lattes = lattes or {}
    competencias = lattes.get("competencias") or {}
    areas_lattes = competencias.get("areas") or []
    linhas_pesquisa = competencias.get("linhas_pesquisa") or []
    palavras_chave = competencias.get("palavras_chave") or []

    termos_ja_estruturados = {
        normalizar_texto(valor)
        for area in areas_lattes
        for valor in (area.get("area"), area.get("subarea"), area.get("especialidade"))
        if valor
    }
    topicos_interesse = unificar_topicos(
        sigaa.get("areasInteresse"),
        linhas_pesquisa,
        palavras_chave,
        excluir=termos_ja_estruturados,
    )

    print(f"Unificando: {sigaa.get('nome')}")
    disciplinas = resolver_disciplinas(
        sigaa.get("disciplinasSigaa") or [], catalogo_disciplinas
    )
    trabalhos_ic = resolver_trabalhos_ic(
        sigaa.get("trabalhosIniciacaoCientifica") or [], catalogo_trabalhos
    )

    return {
        "nome": sigaa.get("nome"),
        "idLattes": sigaa.get("idLattes"),
        "siape": sigaa.get("siape"),
        "resumo": unificar_resumo(lattes.get("resumo"), sigaa.get("descricaoPessoal")),
        "formacaoAcademicaProfissional": sigaa.get("formacaoAcademicaProfissional"),
        "areasEspecializacao": areas_lattes,
        "topicosInteresse": topicos_interesse,
        "producoes": lattes.get("producoes") or [],
        "projetos": lattes.get("projetos") or [],
        "orientacoes": lattes.get("orientacoes") or [],
        "disciplinas": disciplinas,
        "trabalhosIniciacaoCientifica": trabalhos_ic,
    }


def campos_textuais_para_embedding(perfil: dict) -> list[str]:
    """Extrai só o texto que efetivamente vale a pena mandar pro BGE-M3.

    Serve tanto para a validação abaixo quanto de referência para a etapa de
    geração de embeddings propriamente dita: identificadores (nome, idLattes,
    siape) e IDs crus não têm valor semântico e não devem ser tratados como
    texto para gerar embedding.
    """
    partes: list[str] = []

    if perfil.get("resumo"):
        partes.append(perfil["resumo"])
    if perfil.get("formacaoAcademicaProfissional"):
        partes.append(perfil["formacaoAcademicaProfissional"])
    partes.extend(perfil.get("topicosInteresse") or [])

    for area in perfil.get("areasEspecializacao") or []:
        # Uma string por entrada (não uma por campo): é normal a mesma área
        # se repetir entre subáreas irmãs (ex.: mesma área, subáreas
        # diferentes) — isso não é duplicata, é a granularidade da estrutura.
        campos = [
            v for v in (area.get("area"), area.get("subarea"), area.get("especialidade"))
            if v
        ]
        if campos:
            partes.append(" - ".join(campos))
    for producao in perfil.get("producoes") or []:
        if producao.get("titulo"):
            partes.append(producao["titulo"])
    for projeto in perfil.get("projetos") or []:
        if projeto.get("nome"):
            partes.append(projeto["nome"])
        if projeto.get("descricao"):
            partes.append(projeto["descricao"])
    for orientacao in perfil.get("orientacoes") or []:
        if orientacao.get("titulo"):
            partes.append(orientacao["titulo"])
    for disciplina in perfil.get("disciplinas") or []:
        if disciplina.get("nome"):
            partes.append(disciplina["nome"])
        if disciplina.get("ementa"):
            partes.append(disciplina["ementa"])
    for trabalho in perfil.get("trabalhosIniciacaoCientifica") or []:
        if trabalho.get("titulo"):
            partes.append(trabalho["titulo"])
        if trabalho.get("resumo"):
            partes.append(trabalho["resumo"])
        partes.extend(trabalho.get("palavrasChaves") or [])

    return partes


def validar_para_embedding(perfil: dict) -> list[str]:
    """Sinaliza problemas que tornariam o embedding do perfil pouco útil."""
    problemas: list[str] = []
    textos = campos_textuais_para_embedding(perfil)

    if not textos:
        problemas.append("nenhum campo textual — embedding não teria conteúdo real")
        return problemas

    if not perfil.get("resumo"):
        problemas.append("sem resumo (nem Lattes nem SIGAA)")
    if not perfil.get("topicosInteresse") and not perfil.get("areasEspecializacao"):
        problemas.append("sem tópicos de interesse nem áreas de especialização")

    # Duplicata em topicosInteresse: a única lista que construímos com
    # deduplicação garantida (unificar_topicos), então repetição aqui indica
    # uma regressão real no código, não uma característica normal do dado.
    #
    # Não checamos isso em disciplinas/producoes/orientacoes: o mesmo nome de
    # disciplina pode se repetir legitimamente sob códigos/ementas diferentes
    # (grade curricular mudou ao longo do tempo), e o mesmo título de
    # produção/orientação pode se repetir entre anos (ex.: bolsa de IC
    # renovada) ou entre as duas listas (o professor publicou sobre um
    # trabalho que também orientou) — em nenhum desses casos é redundância a
    # eliminar, é histórico acadêmico real.
    topicos_norm = [t.lower() for t in (perfil.get("topicosInteresse") or [])]
    if len(topicos_norm) != len(set(topicos_norm)):
        problemas.append("'topicosInteresse' tem item repetido (bug na deduplicação)")

    # Texto residual que é só um número/código (sinal de que algum ID vazou
    # para um campo textual em vez de ser resolvido).
    for texto in textos:
        if texto.strip().isdigit():
            problemas.append(f"campo textual contém só dígitos: '{texto}'")

    return problemas


def executar_unificacao(
    perfis_sigaa: str = DEFAULT_PERFIS_SIGAA,
    perfis_lattes: str = DEFAULT_PERFIS_LATTES,
    componentes_iesti: str = DEFAULT_COMPONENTES_IESTI,
    componentes_externos: str = DEFAULT_COMPONENTES_EXTERNOS,
    trabalhos_ic: str = DEFAULT_TRABALHOS_IC,
    prefixo_saida: str = DEFAULT_PREFIXO_SAIDA,
) -> None:
    """Função utilizada pelo Airflow e pela CLI."""
    sigaa_registros = ler_parquet_silver(perfis_sigaa)
    lattes_registros = ler_parquet_silver(perfis_lattes)

    catalogo_componentes = construir_catalogo(
        ler_parquet_silver(componentes_iesti),
        ler_parquet_silver(componentes_externos),
        chave_id="idSigaa",
    )
    catalogo_trabalhos = construir_catalogo(
        ler_parquet_silver(trabalhos_ic), chave_id="id"
    )

    lattes_por_id: dict[str, dict] = {
        registro["idLattes"]: registro
        for registro in lattes_registros
        if registro.get("idLattes")
    }

    perfis_com_problema: dict[str, list[str]] = {}
    total = 0
    for sigaa in sigaa_registros:
        lattes = lattes_por_id.get(sigaa.get("idLattes")) if sigaa.get("idLattes") else None
        perfil = montar_perfil_unificado(
            sigaa, lattes, catalogo_componentes, catalogo_trabalhos
        )

        problemas = validar_para_embedding(perfil)
        if problemas:
            perfis_com_problema[perfil["nome"]] = problemas

        chave = f"{prefixo_saida}/{identificador_professor(perfil)}.json"
        salvar_json_gold(chave, perfil)
        total += 1

    print(f"\n{total} perfil(is) unificado(s) e salvo(s) em gold/{prefixo_saida}/.")
    if perfis_com_problema:
        print(
            f"\nAVISO: {len(perfis_com_problema)} perfil(is) com possíveis "
            "problemas para geração de embedding:"
        )
        for nome, problemas in perfis_com_problema.items():
            print(f"  - {nome}: {'; '.join(problemas)}")
    else:
        print("Todos os perfis têm conteúdo textual válido para o BGE-M3.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unifica os perfis SIGAA + Lattes da Silver num perfil por professor na Gold."
    )
    parser.add_argument("--perfis-sigaa", default=DEFAULT_PERFIS_SIGAA)
    parser.add_argument("--perfis-lattes", default=DEFAULT_PERFIS_LATTES)
    parser.add_argument("--componentes-iesti", default=DEFAULT_COMPONENTES_IESTI)
    parser.add_argument("--componentes-externos", default=DEFAULT_COMPONENTES_EXTERNOS)
    parser.add_argument("--trabalhos-ic", default=DEFAULT_TRABALHOS_IC)
    parser.add_argument("--prefixo-saida", default=DEFAULT_PREFIXO_SAIDA)
    args = parser.parse_args()

    executar_unificacao(
        perfis_sigaa=args.perfis_sigaa,
        perfis_lattes=args.perfis_lattes,
        componentes_iesti=args.componentes_iesti,
        componentes_externos=args.componentes_externos,
        trabalhos_ic=args.trabalhos_ic,
        prefixo_saida=args.prefixo_saida,
    )


if __name__ == "__main__":
    main()
