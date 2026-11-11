from bronze.scraping.scrape_trabalhos_ic import indexar_trabalhos_anteriores


def test_indexa_por_url_e_ignora_registros_sem_url_ou_nao_informados():
    anterior = [
        {"titulo": "A", "url": "https://x/1", "resumo": "r", "palavrasChaves": ["k"]},
        {"titulo": "B", "resumo": "sem url (coleta antiga)"},
        {"titulo": "C", "url": "Não informado"},
    ]
    indice = indexar_trabalhos_anteriores(anterior)
    assert list(indice) == ["https://x/1"]
    assert indice["https://x/1"]["resumo"] == "r"


def test_sem_coleta_anterior_indice_vazio():
    assert indexar_trabalhos_anteriores(None) == {}


def test_orientacao_descarta_rotulo_e_nome_do_aluno_no_titulo():
    from silver.integracao.limpar_perfis import transformar_orientacoes

    orientacoes = {"concluidas": {"iniciacao_cientifica": [
        {"titulo": "Tipo:", "orientando": "Ana. Outro texto", "ano_inicio": 2022},
        {"titulo": "Ana Souza", "orientando": "Ana Souza", "ano_inicio": 2022},
        {"titulo": "Tema válido", "orientando": "Ana Souza", "ano_inicio": 2022},
    ]}}
    assert [o["titulo"] for o in transformar_orientacoes(orientacoes)] == ["Tema válido"]


def test_catalogo_mantem_trabalho_sem_orientador_no_roster(monkeypatch):
    from silver.integracao import limpar_perfis as lp

    monkeypatch.setattr(lp, "ler_json_bronze_recente", lambda _: [
        {"titulo": "A", "autores": "Aluno, Maria Silva", "ano": 2024},
        {"titulo": "B", "autores": "Aluno, Pessoa Externa", "ano": 2024},
        {"titulo": "B", "autores": "Aluno, Pessoa Externa", "ano": 2024},
    ])
    por_siape, catalogo = lp.processar_trabalhos_ic("x", [{"nome": "Maria Silva", "siape": "1"}])
    assert [t["titulo"] for t in catalogo] == ["A", "B"]
    assert len(por_siape["1"]) == 1


def test_normalizar_disciplinas_ordena_da_mais_recente():
    from silver.integracao.limpar_perfis import normalizar_disciplinas

    ministradas = [
        {"idSigaa": "antiga", "periodo": "2019.2"},
        {"idSigaa": "nova", "periodo": "2025.1"},
        {"idSigaa": "antiga", "periodo": "2024.2"},
        {"idSigaa": "nova", "periodo": "2025.1"},
        {"idSigaa": "so_ano", "periodo": "2024"},
        {"idSigaa": None, "periodo": "2026.1"},
    ]
    assert normalizar_disciplinas(ministradas) == ["nova", "antiga", "so_ano"]
