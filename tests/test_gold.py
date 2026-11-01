import pytest

from gold import unificar_perfis as g


def test_extrair_subareas_remove_grande_area_e_repeticao():
    areas = [
        {"grande_area": "Engenharias", "area": "Engenharia Elétrica", "subarea": "Circuitos Eletrônicos"},
        {"grande_area": "Engenharias", "area": "Engenharia Elétrica", "subarea": "circuitos eletrônicos"},
        {"grande_area": "Engenharias", "area": "Engenharia de Produção", "subarea": None},
    ]
    assert g.extrair_subareas(areas) == ["Circuitos Eletrônicos", "Engenharia de Produção"]


def test_ids_unicos_preserva_ordem_e_ignora_vazios():
    assert g.ids_unicos(["b", "a", "b", None, "", "a"]) == ["b", "a"]
    assert g.ids_unicos(None) == []


def test_registrar_itens_guarda_no_catalogo_e_devolve_ids():
    catalogo: dict[str, dict] = {}
    itens = [
        {"id": "p1", "nome": "A", "tipo": "pesquisa", "situacao": "x", "ano_inicio": 2020, "ano_conclusao": 2022},
        {"id": "p1", "nome": "A", "tipo": "pesquisa"},
        {"nome": "sem id"},
    ]
    ids = g.registrar_itens(itens, catalogo, g.CAMPOS_PROJETO)
    assert ids == ["p1"]
    assert catalogo["p1"] == {"id": "p1", "nome": "A", "tipo": "pesquisa", "descricao": None, "ano_conclusao": 2022}


def test_unificar_topicos_quebra_virgula_e_deduplica():
    r = g.unificar_topicos(["Usabilidade, Equipamentos Médicos"], ["usabilidade", "Ergonomia"])
    assert r == ["Usabilidade", "Equipamentos Médicos", "Ergonomia"]


def test_unificar_resumo():
    assert g.unificar_resumo("Texto.", "texto.") == "Texto."
    assert g.unificar_resumo("A", "B") == "A\n\nB"
    assert g.unificar_resumo(None, None) is None


def test_identificador_professor_usa_siape_e_exige_valor():
    assert g.identificador_professor({"siape": 123, "idLattes": "x"}) == "123"
    with pytest.raises(ValueError):
        g.identificador_professor({"nome": "Sem Siape", "idLattes": "x"})


def test_validar_referencias_aponta_ids_sem_catalogo():
    perfis = [{"siape": "1", "producoes": ["a", "b"], "disciplinas": ["d1"]}]
    orfas, total = g.validar_referencias(perfis, {"producoes": {"a"}, "disciplinas": {"d1"}})
    assert total == 3
    assert orfas == {"1": ["producoes:b"]}


def test_montar_perfil_referencia_por_id():
    sigaa = {
        "nome": "Fulano", "idLattes": "1", "siape": "10",
        "areasInteresse": ["Robótica"], "disciplinasSigaa": ["5", "5", "6"],
        "trabalhosIniciacaoCientifica": ["ic1"],
    }
    lattes = {
        "resumo": "Resumo",
        "competencias": {"areas": [{"grande_area": "E", "area": "EE", "subarea": "Robótica Móvel"}]},
        "producoes": [{"id": "pr1", "titulo": "T", "ano": 2024, "tipo": "x"}],
        "projetos": [{"id": "pj1", "nome": "N", "tipo": "pesquisa", "situacao": "x"}],
        "orientacoes": [{"id": "o1", "titulo": "O"}],
    }
    prod, proj, ori, ic = {}, {}, {}, {}
    perfil = g.montar_perfil_unificado(
        sigaa, lattes, {"ic1": {"id": "ic1", "titulo": "IC"}}, prod, proj, ori, ic
    )
    assert perfil["areasEspecializacao"] == ["Robótica Móvel"]
    assert perfil["disciplinas"] == ["5", "6"]
    assert perfil["producoes"] == ["pr1"] and "pr1" in prod
    assert perfil["projetos"] == ["pj1"] and "situacao" not in proj["pj1"]
    assert perfil["orientacoes"] == ["o1"] and "o1" in ori
    assert perfil["trabalhosIniciacaoCientifica"] == ["ic1"] and ic["ic1"]["titulo"] == "IC"


def test_publicacao_move_ponteiro_so_no_fim_e_limpa_runs_antigas(s3):
    perfil = {"siape": "10", "nome": "F"}
    for run in ("20261001T000000Z", "20261002T000000Z", "20261003T000000Z", "20261004T000000Z"):
        g.publicar_execucao(run, "perfil_professores", [perfil], {"producoes.json": []})
    removidas = g.limpar_execucoes_antigas(manter=3)
    assert removidas == ["20261001T000000Z"]

    ponteiro = g.GOLD.ler_json(g.CHAVE_PONTEIRO)
    assert ponteiro["run"] == "20261004T000000Z"
    assert g.GOLD.existe("runs/20261004T000000Z/perfil_professores/10.json")
    assert not g.GOLD.existe("runs/20261001T000000Z/perfil_professores/10.json")


def test_aviso_de_embedding_resolve_ids_pelos_catalogos():
    perfil = {"resumo": None, "topicosInteresse": [], "areasEspecializacao": [], "producoes": ["a"]}
    textos = g.campos_textuais_para_embedding(perfil, {"producoes": {"a": {"titulo": "Título"}}})
    assert textos == ["Título"]
    assert "sem resumo (nem Lattes nem SIGAA)" in g.validar_para_embedding(
        perfil, {"producoes": {"a": {"titulo": "Título"}}}
    )


def test_disciplinas_referenciadas_resolve_ids_e_uniformiza_campos():
    catalogo = {
        "5": {"idSigaa": "5", "codigo": "A", "nome": "Interna", "cargaHoraria": "32h", "ementa": "texto"},
        "6": {"idSigaa": "6", "codigo": "B", "nome": "Externa", "cargaHoraria": "45h"},
        "7": {"idSigaa": "7", "codigo": "C", "nome": "Sem professor", "cargaHoraria": "45h"},
    }
    perfis = [{"disciplinas": ["5", "6"]}, {"disciplinas": ["6", "ausente"]}]

    assert g.disciplinas_referenciadas(perfis, catalogo) == [
        {"idSigaa": "5", "codigo": "A", "nome": "Interna", "cargaHoraria": "32h", "ementa": "texto"},
        {"idSigaa": "6", "codigo": "B", "nome": "Externa", "cargaHoraria": "45h", "ementa": None},
    ]


def test_unificar_resumo_nao_repete_frases_entre_fontes():
    assert g.unificar_resumo("Atua em redes. Pesquisa IoT", "Pesquisa IoT. Leciona redes.") == (
        "Atua em redes. Pesquisa IoT\n\nLeciona redes."
    )


def test_formacao_do_resumo_so_entra_se_sigaa_nao_informar():
    base = {"nome": "F", "siape": "1"}
    lattes = {"formacaoResumo": "Doutor pela UNIFEI."}
    montar = lambda sigaa: g.montar_perfil_unificado(sigaa, lattes, {}, {}, {}, {}, {})
    assert montar(base)["formacaoAcademicaProfissional"] == "Doutor pela UNIFEI."
    assert montar(base | {"formacaoAcademicaProfissional": "SIGAA"})["formacaoAcademicaProfissional"] == "SIGAA"
