from storage.minio_storage import ler_json_gold
from recuperacao.sistema_de_busca.indexacao.perfis import criar_perfis, _ano
from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant, garantir_colecao, filtrar_alterados, upsert_perfis
from recuperacao.sistema_de_busca.modelo import gerar_embeddings, carregar_modelo
from recuperacao.sistema_de_busca.textos import (
    producao_montar_texto_para_modelo,
    ics_montar_texto_para_modelo,
    professor_montar_texto_para_modelo,
    projeto_montar_texto_para_modelo,
    orientacao_montar_texto_para_modelo
)
from dotenv import load_dotenv
from recuperacao.sistema_de_busca.indexacao.relacoes import construir_relacoes, professores_por_objeto
from recuperacao.sistema_de_busca import config

load_dotenv()

from storage.minio_storage import ultima_run_gold, ler_jsons_gold, GOLD

def indexar_colecao(client, modelo, nome: str, perfis: list[dict], tamanho_bloco: int = 32,campos_inteiros: tuple[str, ...] = ()) -> None:
    garantir_colecao(client, nome,campos_inteiros)
    novos = filtrar_alterados(client, nome, perfis)
    print(f"{nome}: {len(perfis)} perfis, {len(novos)} novos/alterados")

    for i in range(0, len(novos), tamanho_bloco):
        bloco = novos[i:i + tamanho_bloco]
        embeddings = gerar_embeddings(modelo, bloco)
        upsert_perfis(client, nome, bloco, embeddings)
        print(f"  {nome}: {min(i + tamanho_bloco, len(novos))}/{len(novos)}")
        
def main() -> None:
    run = ultima_run_gold()
    print("Run:", run)

    professores = ler_jsons_gold(f"{run}perfil_professores")
    ics = ler_json_gold(f"{run}trabalhos_ic.json")
    producoes = ler_json_gold(f"{run}producoes.json")
    projetos = ler_json_gold(f"{run}projetos.json")
    orientacoes = ler_json_gold(f"{run}orientacoes.json")
    
    relacoes = construir_relacoes(professores)
    mapa_ic = professores_por_objeto(relacoes, "ic")
    mapa_projeto = professores_por_objeto(relacoes, "projeto")
    mapa_producoes = professores_por_objeto(relacoes, "producao")
    mapa_orientacoes = professores_por_objeto(relacoes, "orientacao")
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
    
    perfis_producoes = criar_perfis(
        producoes, producao_montar_texto_para_modelo, "id",
        lambda p: {"titulo": p.get("titulo"),"ano": _ano(p.get("ano")), "tipo": p.get("tipo")}, mapa_producoes,
    )
        
    perfis_orientacoes = criar_perfis(
        orientacoes, orientacao_montar_texto_para_modelo, "id",
        lambda p: {"titulo": p.get("titulo"),"ano": _ano(p.get("ano_inicio")), "tipo": p.get("tipo")}, mapa_orientacoes,
    )
    #perfis_disciplinas = criar_perfis_disciplinas(disciplinas, mapa_disciplina)

    client = conectar_Qdrant()
    modelo = carregar_modelo()

    indexar_colecao(client, modelo, config.COLLECTION_PROFESSORES, perfis_professores, )
    indexar_colecao(client, modelo, config.COLLECTION_ICS, perfis_ics, campos_inteiros=("ano",))
    indexar_colecao(client, modelo, config.COLLECTION_PROJETOS, perfis_projetos, campos_inteiros=("ano",))
    indexar_colecao(client, modelo, config.COLLECTION_PRODUCAO, perfis_producoes, campos_inteiros=("ano",))
    indexar_colecao(client, modelo, config.COLLECTION_ORIENTADOR, perfis_orientacoes, campos_inteiros=("ano",))

    # indexar_colecao(client, modelo, config.COLLECTION_DISCIPLINAS, perfis_disciplinas)

if __name__ == "__main__":
    main()