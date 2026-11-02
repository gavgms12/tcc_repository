import pandas as pd
from transformers import AutoTokenizer
from storage.minio_storage import ler_json_gold
from recuperacao.sistema_de_busca.indexacao.perfis import criar_perfis, _ano
from recuperacao.sistema_de_busca.textos import (
    producao_montar_texto_para_modelo,
    ics_montar_texto_para_modelo,
    professor_montar_texto_para_modelo,
    projeto_montar_texto_para_modelo,
    orientacao_montar_texto_para_modelo
)
from recuperacao.sistema_de_busca.indexacao.relacoes import construir_relacoes, professores_por_objeto
from storage.minio_storage import ultima_run_gold, ler_jsons_gold, GOLD

def contar_tokens(tokanizer,perfis: list[dict]) -> pd.Series:
    ids = tokanizer([p["texto"] for p in perfis], truncation=False)["input_ids"]
    return pd.Series([len(i) for i in ids], index=[p["id"] for p in perfis])

def resumo_tokens(tokanizer, nome: str, perfis: list[dict]) -> None:
    tokens = contar_tokens(tokanizer, perfis)
    print(f"\n{nome}: {len(tokens)} textos")
    print(tokens.describe(percentiles=[0.5, 0.9, 0.99]).round(0).to_string())
    print("acima de 512: ", (tokens > 512).sum())
    print("acima de 1024:", (tokens > 1024).sum())
    
def main() -> None:
    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
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
    resumo_tokens(tokenizer,"professores", perfis_professores)
    resumo_tokens(tokenizer, "ics", perfis_ics)
    resumo_tokens(tokenizer, "projetos", perfis_projetos)
    resumo_tokens(tokenizer, "orientacoes", perfis_orientacoes)
    resumo_tokens(tokenizer, "producoes", perfis_producoes)

    # para o reranker conta para o uso de tokens a query e o documento
    consulta = "Quero desenvolver um projeto de programação embarcada usando microcontroladores"
    n_consulta = len(tokenizer(consulta)["input_ids"])

    tokens = contar_tokens(tokenizer, perfis_professores)
    print("Limite para o documento:", 512 - n_consulta)
    print("Cortados no reranker:", (tokens > 512 - n_consulta).sum(), "de", len(tokens))

if __name__ == "__main__":
    main()