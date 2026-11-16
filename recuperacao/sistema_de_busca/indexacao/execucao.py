import argparse

from src.storage.minio_storage import ler_json_gold
from recuperacao.sistema_de_busca.indexacao.perfis import criar_perfis, _ano
from recuperacao.sistema_de_busca.database_vetores import (
    conectar_Qdrant, garantir_colecao, filtrar_alterados, upsert_perfis, atualizar_m, remover_ausentes,
)
from recuperacao.sistema_de_busca.modelo import gerar_embeddings, carregar_modelo
from recuperacao.sistema_de_busca.textos import (
    producao_montar_texto_para_modelo,
    ics_montar_texto_para_modelo,
    professor_montar_texto_para_modelo,
    projeto_montar_texto_para_modelo,
    orientacao_montar_texto_para_modelo,
    disciplina_montar_texto_para_modelo
)
from dotenv import load_dotenv
from recuperacao.sistema_de_busca.indexacao.relacoes import construir_relacoes, professores_por_objeto
from recuperacao.sistema_de_busca import config

load_dotenv()

import os

from src.storage.minio_storage import GOLD


def ultima_run_gold() -> str:
    """Prefixo da run atual da Gold, ex.: 'runs/20261112T002444Z/'.

    Usa o ponteiro current.json (só é atualizado quando a run termina inteira).
    GOLD_RUN=<run_id> fixa uma run específica (reprocessar, testes)."""
    fixa = os.getenv("GOLD_RUN")
    if fixa:
        return f"runs/{fixa}/"
    ponteiro = GOLD.ler_json("current.json")
    return ponteiro["prefixo"].rstrip("/") + "/"


def ler_jsons_gold(prefixo: str) -> list[dict]:
    """Lê todos os .json sob `prefixo` na Gold (ex.: os perfis de professores)."""
    prefixo = prefixo.rstrip("/") + "/"
    return [GOLD.ler_json(chave) for chave in sorted(GOLD.listar(prefixo)) if chave.lower().endswith(".json")]

def indexar_colecao(client, modelo, nome: str, perfis: list[dict], tamanho_bloco: int = 32,campos_inteiros: tuple[str, ...] = (),
                    exclusao: str = "sim", forcar_exclusao: bool = False) -> None:
    """exclusao: "sim" apaga do Qdrant o que sumiu dos dados, "simular" só lista, "nao" não verifica."""
    garantir_colecao(client, nome,campos_inteiros)
    novos = filtrar_alterados(client, nome, perfis)
    print(f"{nome}: {len(perfis)} perfis, {len(novos)} novos/alterados")

    for i in range(0, len(novos), tamanho_bloco):
        bloco = novos[i:i + tamanho_bloco]
        embeddings = gerar_embeddings(modelo, bloco)
        upsert_perfis(client, nome, bloco, embeddings)
        print(f"  {nome}: {min(i + tamanho_bloco, len(novos))}/{len(novos)}")

    if exclusao != "nao":
        remover_ausentes(client, nome, [p["id"] for p in perfis],
                         simular=(exclusao == "simular"), forcar=forcar_exclusao)


def _argumentos():
    parser = argparse.ArgumentParser(description="Indexa a última run da gold no Qdrant (insere, atualiza e remove).")
    parser.add_argument("--exclusao", choices=["sim", "simular", "nao"], default="sim",
                        help="apagar do Qdrant os itens que não estão mais na gold (padrão: sim); "
                             "'simular' só lista o que seria apagado")
    parser.add_argument("--forcar-exclusao", action="store_true",
                        help="apaga mesmo quando passa de 30%% da coleção (cuidado: run da gold incompleta apagaria tudo)")
    return parser.parse_args()


def main() -> None:
    args = _argumentos()
    opcoes = {"exclusao": args.exclusao, "forcar_exclusao": args.forcar_exclusao}
    run = ultima_run_gold()
    print("Run:", run)

    professores = ler_jsons_gold(f"{run}perfil_professores")
    ics = ler_json_gold(f"{run}trabalhos_ic.json")
    producoes = ler_json_gold(f"{run}producoes.json")
    projetos = ler_json_gold(f"{run}projetos.json")
    orientacoes = ler_json_gold(f"{run}orientacoes.json")
    disciplinas = ler_json_gold(f"{run}disciplinas.json")

    relacoes = construir_relacoes(professores)
    mapa_ic = professores_por_objeto(relacoes, "ic")
    mapa_projeto = professores_por_objeto(relacoes, "projeto")
    mapa_producoes = professores_por_objeto(relacoes, "producao")
    mapa_orientacoes = professores_por_objeto(relacoes, "orientacao")
    mapa_disciplina = professores_por_objeto(relacoes, "disciplina")
    perfis_ics = criar_perfis(
        ics, ics_montar_texto_para_modelo, "id",
        lambda t: {"titulo": t.get("titulo"), "ano": _ano(t.get("ano"))},
        mapa_ic,
    )

    perfis_projetos = criar_perfis(
        projetos, projeto_montar_texto_para_modelo, "id",
        lambda p: {"nome": p.get("nome"), "tipo": p.get("tipo"), "ano": _ano(p.get("ano_conclusao"))},
        mapa_projeto,
    )

    perfis_professores = criar_perfis(
        professores, professor_montar_texto_para_modelo, "siape",
        lambda p: {"nome": p["nome"]},
    )
    
    perfis_producoes = criar_perfis(
        producoes, producao_montar_texto_para_modelo, "id",
        lambda p: {"titulo": p.get("titulo"),"ano": _ano(p.get("ano")), "tipo": p.get("tipo")}, mapa_producoes,
    )
        
    perfis_orientacoes = criar_perfis(
        orientacoes, orientacao_montar_texto_para_modelo, "id",
        lambda p: {"titulo": p.get("titulo"),"ano": _ano(p.get("ano_inicio")), "tipo": p.get("tipo")}, mapa_orientacoes,
    )
    perfis_disciplinas = criar_perfis(
            disciplinas, disciplina_montar_texto_para_modelo, "idSigaa",
            lambda p: {"codigo": p.get("codigo"), "nome": p.get("nome")}, mapa_disciplina,
        )
    client = conectar_Qdrant()
    modelo = carregar_modelo()

    indexar_colecao(client, modelo, config.COLLECTION_PROFESSORES, perfis_professores, **opcoes)
    indexar_colecao(client, modelo, config.COLLECTION_ICS, perfis_ics, campos_inteiros=("ano",), **opcoes)
    indexar_colecao(client, modelo, config.COLLECTION_PROJETOS, perfis_projetos, campos_inteiros=("ano",), **opcoes)
    indexar_colecao(client, modelo, config.COLLECTION_PRODUCAO, perfis_producoes, campos_inteiros=("ano",), **opcoes)
    indexar_colecao(client, modelo, config.COLLECTION_ORIENTADOR, perfis_orientacoes, campos_inteiros=("ano",), **opcoes)
    indexar_colecao(client, modelo, config.COLLECTION_DISCIPLINAS, perfis_disciplinas, **opcoes)

    atualizar_m(16,client, config.COLLECTION_PROFESSORES)
    atualizar_m(16,client, config.COLLECTION_ICS)
    atualizar_m(16,client, config.COLLECTION_PROJETOS)
    atualizar_m(16,client, config.COLLECTION_PRODUCAO)
    atualizar_m(16,client, config.COLLECTION_ORIENTADOR)
    atualizar_m(16,client, config.COLLECTION_DISCIPLINAS)

    # indexar_colecao(client, modelo, config.COLLECTION_DISCIPLINAS, perfis_disciplinas)

if __name__ == "__main__":
    main()