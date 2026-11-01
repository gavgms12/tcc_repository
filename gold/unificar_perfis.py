#!/usr/bin/env python3
"""Unifica os perfis SIGAA + Lattes já limpos (Silver) num perfil por professor.

Lê `perfis_sigaa_limpos.parquet` e `perfis_lattes_limpos.parquet` da Silver e
os funde num único documento por professor. O perfil referencia por ID as
produções, projetos, disciplinas e trabalhos de IC, cujo conteúdo completo
fica em arquivos separados no bucket Gold (`producoes.json`, `projetos.json`,
`orientacoes.json`, `disciplinas.json`, `trabalhos_ic.json`).
Deduplica tópicos/áreas de interesse que aparecem nas duas fontes e evita
repetir o mesmo resumo duas vezes. Cada perfil final é salvo como um JSON
próprio no bucket Gold, sob o prefixo `perfil_professores/`.

Ao final, valida se cada perfil resultante tem conteúdo textual suficiente
para gerar um embedding útil no BGE-M3 (perfis "vazios" — sem resumo, sem
tópicos, sem nenhuma produção/disciplina resolvida — são reportados, não
descartados silenciosamente).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.log import configurar_logging
from common.texto import chave_frase, dividir_frases, normalizar_texto
from storage.minio_storage import GOLD, data_no_fuso_coleta, ler_parquet_silver

logger = logging.getLogger(__name__)

DEFAULT_PERFIS_SIGAA = "perfis_sigaa_limpos.parquet"
DEFAULT_PERFIS_LATTES = "perfis_lattes_limpos.parquet"
DEFAULT_COMPONENTES_IESTI = "componentes_curriculares.parquet"
DEFAULT_COMPONENTES_EXTERNOS = "componentes_curriculares_externos.parquet"
DEFAULT_TRABALHOS_IC = "trabalhos_ic_periodicos.parquet"
DEFAULT_PREFIXO_SAIDA = "perfil_professores"
CHAVE_PRODUCOES = "producoes.json"
CHAVE_PROJETOS = "projetos.json"
CHAVE_ORIENTACOES = "orientacoes.json"
CHAVE_DISCIPLINAS = "disciplinas.json"
CHAVE_TRABALHOS_IC = "trabalhos_ic.json"
CAMPOS_PROJETO = ("id", "nome", "tipo", "descricao", "ano_conclusao")
CAMPOS_DISCIPLINA = ("idSigaa", "codigo", "nome", "cargaHoraria", "ementa")

# Cada execução grava tudo sob runs/<run_id>/ e só então atualiza current.json,
# que aponta para a execução válida; consumidores nunca veem estado parcial.
PREFIXO_RUNS = "runs"
CHAVE_PONTEIRO = "current.json"
FORMATO_RUN_ID = "%Y%m%dT%H%M%SZ"
DIAS_MANTIDOS = 3
# Fração máxima de referências sem catálogo tolerada antes de falhar a Gold.
MAX_TAXA_REFERENCIAS_ORFAS = 0.02


class PerfilGold(TypedDict):
    nome: str | None
    idLattes: str | None
    siape: str
    resumo: str | None
    formacaoAcademicaProfissional: str | None
    areasEspecializacao: list[str]
    topicosInteresse: list[str]
    producoes: list[str]
    projetos: list[str]
    orientacoes: list[str]
    disciplinas: list[str]
    trabalhosIniciacaoCientifica: list[str]


def identificador_professor(perfil: dict) -> str:
    """Chave estável do perfil: o siape existe para todos os docentes e não
    muda quando o idLattes passa a ser conhecido (o que duplicaria o arquivo)."""
    if not perfil.get("siape"):
        raise ValueError(f"Perfil sem siape, sem chave estável: {perfil.get('nome')}")
    return str(perfil["siape"])


def construir_catalogo(*parquets: list[dict], chave_id: str) -> dict[str, dict]:
    """Indexa uma lista de registros (de um ou mais catálogos) pelo campo id."""
    catalogo: dict[str, dict] = {}
    for registros in parquets:
        for registro in registros:
            id_registro = registro.get(chave_id)
            if id_registro and id_registro not in catalogo:
                catalogo[id_registro] = registro
    return catalogo


def ids_unicos(ids: list[str] | None) -> list[str]:
    """Remove IDs repetidos preservando a ordem."""
    return list(dict.fromkeys(i for i in ids or [] if i))


def extrair_subareas(areas: list[dict]) -> list[str]:
    """Reduz as áreas do Lattes às subáreas: `grande_area` e `area` se
    repetiam em todas as entradas. Quando não há subárea, cai para a
    especialidade e, por último, para a própria área."""
    subareas: list[str] = []
    vistas: set[str] = set()
    for area in areas or []:
        texto = normalizar_texto(
            area.get("subarea") or area.get("especialidade") or area.get("area")
        )
        if texto and texto.lower() not in vistas:
            vistas.add(texto.lower())
            subareas.append(texto)
    return subareas


def registrar_itens(
    itens: list[dict], destino: dict[str, dict], campos: tuple[str, ...] | None = None
) -> list[str]:
    """Guarda cada item no catálogo `destino` (por id) e devolve só os IDs."""
    ids: list[str] = []
    for item in itens or []:
        id_item = item.get("id")
        if not id_item:
            continue
        if id_item not in destino:
            destino[id_item] = (
                {k: item.get(k) for k in campos} if campos else dict(item)
            )
        ids.append(id_item)
    return ids_unicos(ids)


def disciplinas_referenciadas(
    perfis: list[PerfilGold], catalogo_componentes: dict[str, dict]
) -> list[dict]:
    """Registros das disciplinas citadas nos perfis, sem repetição.

    Os componentes externos ao IESTI não têm ementa na Silver; nesses casos o
    campo `ementa` sai como None, para todo registro ter o mesmo formato.
    """
    usadas: dict[str, dict] = {}
    for perfil in perfis:
        for id_disciplina in perfil["disciplinas"]:
            componente = catalogo_componentes.get(id_disciplina)
            if componente and id_disciplina not in usadas:
                usadas[id_disciplina] = {c: componente.get(c) for c in CAMPOS_DISCIPLINA}
    return list(usadas.values())


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
    """Combina o resumo do Lattes com a descrição pessoal do SIGAA, sem repetir
    as frases que as duas fontes têm em comum."""
    resumo_lattes = normalizar_texto(resumo_lattes)
    frases_lattes = {chave_frase(f) for f in dividir_frases(resumo_lattes)}
    descricao_sigaa = " ".join(
        f for f in dividir_frases(descricao_sigaa) if chave_frase(f) not in frases_lattes
    )

    if resumo_lattes and descricao_sigaa:
        return f"{resumo_lattes}\n\n{descricao_sigaa}"
    return resumo_lattes or descricao_sigaa or None


def montar_perfil_unificado(
    sigaa: dict,
    lattes: dict | None,
    catalogo_trabalhos: dict[str, dict],
    producoes: dict[str, dict],
    projetos: dict[str, dict],
    orientacoes: dict[str, dict],
    trabalhos_ic: dict[str, dict],
) -> PerfilGold:
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

    logger.debug("Unificando: %s", sigaa.get("nome"))
    ids_ic = ids_unicos(sigaa.get("trabalhosIniciacaoCientifica"))
    for id_trabalho in ids_ic:
        info = catalogo_trabalhos.get(id_trabalho)
        if info:
            trabalhos_ic.setdefault(
                id_trabalho, {"id": id_trabalho} | {k: v for k, v in info.items() if k != "id"}
            )

    return {
        "nome": sigaa.get("nome"),
        "idLattes": sigaa.get("idLattes"),
        "siape": sigaa.get("siape"),
        "resumo": unificar_resumo(lattes.get("resumo"), sigaa.get("descricaoPessoal")),
        # As frases de titulação saem do resumo na Silver; viram formação quando
        # o SIGAA não a informa, para a informação não se perder.
        "formacaoAcademicaProfissional": sigaa.get("formacaoAcademicaProfissional")
        or lattes.get("formacaoResumo")
        or sigaa.get("formacaoDescricao"),
        "areasEspecializacao": extrair_subareas(areas_lattes),
        "topicosInteresse": topicos_interesse,
        "producoes": registrar_itens(lattes.get("producoes"), producoes),
        "projetos": registrar_itens(lattes.get("projetos"), projetos, CAMPOS_PROJETO),
        "orientacoes": registrar_itens(lattes.get("orientacoes"), orientacoes),
        "disciplinas": ids_unicos(sigaa.get("disciplinasSigaa")),
        "trabalhosIniciacaoCientifica": ids_ic,
    }


def campos_textuais_para_embedding(perfil: dict, catalogos: dict[str, dict]) -> list[str]:
    """Extrai só o texto que efetivamente vale a pena mandar pro BGE-M3.

    O perfil guarda apenas IDs de produções, projetos, disciplinas e trabalhos
    de IC; `catalogos` (chaves `producoes`, `projetos`, `orientacoes`, `disciplinas`,
    `trabalhosIniciacaoCientifica`, cada uma um dict id -> registro) resolve
    esses IDs para o texto. Identificadores (nome, idLattes, siape) e IDs
    crus não têm valor semântico e não devem virar texto de embedding.
    """
    partes: list[str] = []

    if perfil.get("resumo"):
        partes.append(perfil["resumo"])
    if perfil.get("formacaoAcademicaProfissional"):
        partes.append(perfil["formacaoAcademicaProfissional"])
    partes.extend(perfil.get("topicosInteresse") or [])
    partes.extend(perfil.get("areasEspecializacao") or [])

    def resolver(campo: str) -> list[dict]:
        catalogo = catalogos.get(campo, {})
        return [catalogo[i] for i in perfil.get(campo) or [] if i in catalogo]

    for producao in resolver("producoes"):
        if producao.get("titulo"):
            partes.append(producao["titulo"])
    for projeto in resolver("projetos"):
        if projeto.get("nome"):
            partes.append(projeto["nome"])
        if projeto.get("descricao"):
            partes.append(projeto["descricao"])
    for orientacao in resolver("orientacoes"):
        if orientacao.get("titulo"):
            partes.append(orientacao["titulo"])
    for disciplina in resolver("disciplinas"):
        if disciplina.get("nome"):
            partes.append(disciplina["nome"])
        if disciplina.get("ementa"):
            partes.append(disciplina["ementa"])
    for trabalho in resolver("trabalhosIniciacaoCientifica"):
        if trabalho.get("titulo"):
            partes.append(trabalho["titulo"])
        if trabalho.get("resumo"):
            partes.append(trabalho["resumo"])
        partes.extend(trabalho.get("palavrasChaves") or [])

    return partes


def validar_para_embedding(perfil: dict, catalogos: dict[str, dict]) -> list[str]:
    """Sinaliza problemas que tornariam o embedding do perfil pouco útil."""
    problemas: list[str] = []
    textos = campos_textuais_para_embedding(perfil, catalogos)

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


CAMPOS_REFERENCIA = (
    "producoes",
    "projetos",
    "orientacoes",
    "disciplinas",
    "trabalhosIniciacaoCientifica",
)


def validar_referencias(
    perfis: list[PerfilGold], catalogos: dict[str, set[str]]
) -> tuple[dict[str, list[str]], int]:
    """Confere se todo ID citado nos perfis existe no catálogo correspondente.

    Devolve (órfãs por siape, total de referências verificadas).
    """
    orfas: dict[str, list[str]] = {}
    total = 0
    for perfil in perfis:
        for campo in CAMPOS_REFERENCIA:
            ids = perfil.get(campo) or []
            total += len(ids)
            faltando = [i for i in ids if i not in catalogos.get(campo, set())]
            if faltando:
                orfas.setdefault(perfil["siape"], []).extend(
                    f"{campo}:{i}" for i in faltando
                )
    return orfas, total


def publicar_execucao(
    run_id: str,
    prefixo_saida: str,
    perfis: list[PerfilGold],
    catalogos_json: dict[str, list[dict]],
) -> None:
    """Grava a execução em runs/<run_id>/ e só então move o ponteiro `current`.

    Uma falha no meio deixa o ponteiro apontando para a execução anterior
    (válida) em vez de um conjunto parcial de perfis.
    """
    base = f"{PREFIXO_RUNS}/{run_id}"
    for perfil in perfis:
        GOLD.salvar_json(
            f"{base}/{prefixo_saida}/{identificador_professor(perfil)}.json", perfil
        )
    for nome, itens in catalogos_json.items():
        GOLD.salvar_json(f"{base}/{nome}", itens)

    GOLD.salvar_json(
        CHAVE_PONTEIRO,
        {
            "run": run_id,
            "prefixo": base,
            "perfis": f"{base}/{prefixo_saida}/",
            "total_perfis": len(perfis),
            "catalogos": {nome: f"{base}/{nome}" for nome in catalogos_json},
        },
    )


def dia_da_execucao(run_id: str) -> str:
    """Dia de uma execução no fuso da coleta (o run_id está em UTC)."""
    momento = datetime.strptime(run_id, FORMATO_RUN_ID).replace(tzinfo=timezone.utc)
    return data_no_fuso_coleta(momento)


def limpar_execucoes_antigas(manter_dias: int = DIAS_MANTIDOS) -> list[str]:
    """Mantém só a última execução de cada dia, nos `manter_dias` dias mais
    recentes; remove as demais e devolve os run_ids removidos."""
    run_ids = sorted(
        {chave.split("/")[1] for chave in GOLD.listar(f"{PREFIXO_RUNS}/")}
    )
    ultima_do_dia = {dia_da_execucao(run_id): run_id for run_id in run_ids}
    dias_mantidos = sorted(ultima_do_dia)[-manter_dias:] if manter_dias > 0 else []
    mantidas = {ultima_do_dia[dia] for dia in dias_mantidos}
    antigos = [run_id for run_id in run_ids if run_id not in mantidas]
    for run_id in antigos:
        GOLD.remover(GOLD.listar(f"{PREFIXO_RUNS}/{run_id}/"))
    return antigos


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

    producoes: dict[str, dict] = {}
    projetos: dict[str, dict] = {}
    orientacoes: dict[str, dict] = {}
    trabalhos_ic_usados: dict[str, dict] = {}
    catalogos_validacao = {
        "producoes": producoes,
        "projetos": projetos,
        "orientacoes": orientacoes,
        "disciplinas": catalogo_componentes,
        "trabalhosIniciacaoCientifica": trabalhos_ic_usados,
    }

    perfis: list[PerfilGold] = []
    perfis_com_problema: dict[str, list[str]] = {}
    for sigaa in sigaa_registros:
        lattes = lattes_por_id.get(sigaa.get("idLattes")) if sigaa.get("idLattes") else None
        perfil = montar_perfil_unificado(
            sigaa,
            lattes,
            catalogo_trabalhos,
            producoes,
            projetos,
            orientacoes,
            trabalhos_ic_usados,
        )
        perfis.append(perfil)

        problemas = validar_para_embedding(perfil, catalogos_validacao)
        if problemas:
            perfis_com_problema[f"{perfil['siape']} {perfil['nome']}"] = problemas

    # Integridade referencial: falha antes de publicar qualquer coisa.
    orfas, total_refs = validar_referencias(
        perfis, {campo: set(c) for campo, c in catalogos_validacao.items()}
    )
    if orfas:
        qtd_orfas = sum(len(v) for v in orfas.values())
        taxa = qtd_orfas / max(1, total_refs)
        mensagem = (
            f"{qtd_orfas} de {total_refs} referência(s) sem catálogo "
            f"({taxa:.1%}): {orfas}"
        )
        if taxa > MAX_TAXA_REFERENCIAS_ORFAS:
            raise ValueError(mensagem)
        logger.warning(mensagem)

    disciplinas = disciplinas_referenciadas(perfis, catalogo_componentes)

    run_id = datetime.now(timezone.utc).strftime(FORMATO_RUN_ID)
    publicar_execucao(
        run_id,
        prefixo_saida,
        perfis,
        {
            CHAVE_PRODUCOES: list(producoes.values()),
            CHAVE_PROJETOS: list(projetos.values()),
            CHAVE_ORIENTACOES: list(orientacoes.values()),
            CHAVE_DISCIPLINAS: disciplinas,
            CHAVE_TRABALHOS_IC: list(trabalhos_ic_usados.values()),
        },
    )
    removidas = limpar_execucoes_antigas()

    logger.info(
        "%d perfil(is) unificado(s) em gold/%s/%s/ (current.json atualizado).",
        len(perfis),
        PREFIXO_RUNS,
        run_id,
    )
    logger.info(
        "Catálogos: %d produção(ões), %d projeto(s), %d orientação(ões), "
        "%d disciplina(s), %d trabalho(s) de IC.",
        len(producoes),
        len(projetos),
        len(orientacoes),
        len(disciplinas),
        len(trabalhos_ic_usados),
    )
    if removidas:
        logger.info("Execuções antigas removidas: %s", ", ".join(removidas))

    if perfis_com_problema:
        logger.warning(
            "%d perfil(is) com possíveis problemas para geração de embedding:",
            len(perfis_com_problema),
        )
        for nome, problemas in perfis_com_problema.items():
            logger.warning("  - %s: %s", nome, "; ".join(problemas))
    else:
        logger.info("Todos os perfis têm conteúdo textual válido para o BGE-M3.")


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
    configurar_logging()

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
