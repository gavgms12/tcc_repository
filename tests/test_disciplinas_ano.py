"""Filtro de ano das disciplinas na busca: o ano é do par (professor, disciplina)."""
from types import SimpleNamespace

from recuperacao.sistema_de_busca.busca.disciplinas_tema import (
    ano_min_disciplinas, professores_no_periodo, restringir_ao_periodo,
)


def test_piso_do_ano_das_disciplinas():
    assert ano_min_disciplinas(None, piso=2020) == 2020   # campo vazio
    assert ano_min_disciplinas(2015, piso=2020) == 2020   # ano anterior ao piso
    assert ano_min_disciplinas(2023, piso=2020) == 2023   # ano posterior vale
from recuperacao.sistema_de_busca.indexacao.relacoes import anos_disciplinas


def test_anos_disciplinas_por_professor():
    professores = [
        {"siape": 1, "disciplinasPorAno": {"2025": ["A"], "2017": ["A", "B"]}},
        {"siape": "2", "disciplinasPorAno": {"2018": ["A"]}},
        {"siape": "3"},
    ]
    assert anos_disciplinas(professores) == {
        "A": {"1": [2025, 2017], "2": [2018]},
        "B": {"1": [2017]},
    }


PAYLOAD = {
    "professor_ids": ["1", "2"],
    "anos_professores": {"1": [2025, 2017], "2": [2018]},
}


def test_so_fica_quem_lecionou_no_periodo():
    assert professores_no_periodo(PAYLOAD, ano_min=2020) == ["1"]
    assert professores_no_periodo(PAYLOAD, ano_max=2017) == ["1"]
    assert professores_no_periodo(PAYLOAD, ano_min=2019, ano_max=2024) == []


def test_sem_filtro_ou_indice_antigo_nao_corta():
    assert professores_no_periodo(PAYLOAD) == ["1", "2"]
    antigo = {"professor_ids": ["1", "2"]}
    assert professores_no_periodo(antigo, ano_min=2020) == ["1", "2"]


def test_restringir_altera_os_pontos():
    ponto = SimpleNamespace(payload=dict(PAYLOAD))
    restringir_ao_periodo([ponto], ano_min=2020)
    assert ponto.payload["professor_ids"] == ["1"]
