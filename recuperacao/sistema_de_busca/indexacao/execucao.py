from storage.minio_storage import ler_json_gold
from recuperacao.sistema_de_busca.indexacao.perfis import criar_perfis, _ano
from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant, garantir_colecao, filtrar_alterados, upsert_perfis
from recuperacao.sistema_de_busca.modelo import gerar_embeddings, carregar_modelo
from recuperacao.sistema_de_busca.textos import (
    disciplina_montar_texto_para_modelo,
    ics_montar_texto_para_modelo,
    professor_montar_texto_para_modelo,
    projeto_montar_texto_para_modelo
)
from dotenv import load_dotenv
from recuperacao.sistema_de_busca.indexacao.relacoes import construir_relacoes, professores_por_objeto
from recuperacao.sistema_de_busca import config

load_dotenv()

from storage.minio_storage import ultima_run_gold, ler_jsons_gold, GOLD

def indexar_colecao(client, modelo, nome: str, perfis: list[dict]) -> None:
    garantir_colecao(client, nome)
    novos = filtrar_alterados(client, nome, perfis)
    print(f"{nome}: {len(perfis)} perfis, {len(novos)} novos/alterados")

    if not novos:
        return

    embeddings = gerar_embeddings(modelo, novos)
    upsert_perfis(client, nome, novos, embeddings)

def main() -> None:
    run = ultima_run_gold()
    print("Run:", run)

    professores = ler_jsons_gold(f"{run}perfil_professores")
    ics = ler_json_gold(f"{run}trabalhos_ic.json")
    #disciplinas = ler_json_gold(f"{run}...")   # a definir
    projetos = ler_json_gold(f"{run}projetos.json")

    relacoes = construir_relacoes(professores)
    mapa_ic = professores_por_objeto(relacoes, "ic")
    mapa_projeto = professores_por_objeto(relacoes, "projeto")

    #mapa_disciplina = professores_por_objeto(relacoes, "disciplina")
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
    #perfis_disciplinas = criar_perfis_disciplinas(disciplinas, mapa_disciplina)

    client = conectar_Qdrant()
    modelo = carregar_modelo()

    indexar_colecao(client, modelo, config.COLLECTION_PROFESSORES, perfis_professores)
    indexar_colecao(client, modelo, config.COLLECTION_ICS, perfis_ics)
    indexar_colecao(client, modelo, config.COLLECTION_PROJETOS, perfis_projetos)
    # indexar_colecao(client, modelo, config.COLLECTION_DISCIPLINAS, perfis_disciplinas)


if __name__ == "__main__":
    main()