from bronze.scraping.scrape_sigaa_componentes import aplicar_ementas_anteriores


def test_reaproveita_ementa_e_tipo_da_coleta_anterior():
    anterior = {"componentes": [{"idSigaa": "1", "ementa": "E1", "tipo": "Disciplina"}]}
    atuais = [{"idSigaa": "1"}, {"idSigaa": "3"}]
    assert aplicar_ementas_anteriores(atuais, anterior) == 1
    assert atuais[0] == {
        "idSigaa": "1", "ementa": "E1", "tipo": "Disciplina", "ementaConsultada": True,
    }
    assert "ementaConsultada" not in atuais[1]


def test_componente_consultado_sem_ementa_nao_e_buscado_de_novo():
    anterior = {"componentes": [{"idSigaa": "2", "ementa": None, "ementaConsultada": True}]}
    atuais = [{"idSigaa": "2"}]
    assert aplicar_ementas_anteriores(atuais, anterior) == 1
    assert atuais[0].get("ementaConsultada") is True
    assert "ementa" not in atuais[0]


def test_sem_coleta_anterior_nao_reaproveita_nada():
    assert aplicar_ementas_anteriores([{"idSigaa": "1"}], None) == 0
