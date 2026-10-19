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
