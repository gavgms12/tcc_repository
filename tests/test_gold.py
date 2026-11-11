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
    removidas = g.limpar_execucoes_antigas(manter_dias=3)
    assert removidas == ["20261001T000000Z"]

    ponteiro = g.GOLD.ler_json(g.CHAVE_PONTEIRO)
    assert ponteiro["run"] == "20261004T000000Z"
    assert g.GOLD.existe("runs/20261004T000000Z/perfil_professores/10.json")
    assert not g.GOLD.existe("runs/20261001T000000Z/perfil_professores/10.json")


def test_limpeza_mantem_so_a_ultima_execucao_de_cada_dia(s3, monkeypatch):
    monkeypatch.setenv("TZ_COLETA", "America/Sao_Paulo")
    perfil = {"siape": "10", "nome": "F"}
    # 02:00Z ainda é 23:00 do dia anterior em São Paulo.
    for run in ("20261001T150000Z", "20261001T180000Z", "20261002T020000Z", "20261002T150000Z"):
        g.publicar_execucao(run, "perfil_professores", [perfil], {"producoes.json": []})

    removidas = g.limpar_execucoes_antigas()

    assert removidas == ["20261001T150000Z", "20261001T180000Z"]
    assert g.GOLD.existe("runs/20261002T020000Z/perfil_professores/10.json")
    assert g.GOLD.existe("runs/20261002T150000Z/producoes.json")
    assert g.GOLD.ler_json(g.CHAVE_PONTEIRO)["run"] == "20261002T150000Z"


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


def _perfil_com_iniciacoes(iniciacoes, catalogo, ids_sigaa=(), trabalhos=None):
    sigaa = {"nome": "F", "siape": "10", "trabalhosIniciacaoCientifica": list(ids_sigaa)}
    orientacoes = {}
    trabalhos = {} if trabalhos is None else trabalhos
    perfil = g.montar_perfil_unificado(
        sigaa, {"orientacoes": iniciacoes}, catalogo, {}, {}, orientacoes, trabalhos
    )
    return perfil, orientacoes, trabalhos


def _ic(titulo, ano=2024):
    return {"id": titulo, "tipo": "iniciacao_cientifica", "titulo": titulo, "ano_inicio": ano}


def test_iniciacao_vai_para_trabalhos_ic_e_sai_de_orientacoes():
    tcc = {"id": "t1", "tipo": "tcc", "titulo": "Um TCC", "ano_inicio": 2024}
    perfil, orientacoes, trabalhos = _perfil_com_iniciacoes([tcc, _ic("Só título")], {})
    assert perfil["orientacoes"] == ["t1"] and list(orientacoes) == ["t1"]
    assert len(perfil["trabalhosIniciacaoCientifica"]) == 1
    registro = trabalhos[perfil["trabalhosIniciacaoCientifica"][0]]
    assert registro == {
        "id": registro["id"], "titulo": "Só título", "autores": None,
        "resumo": None, "palavrasChaves": [], "ano": 2024,
    }


def test_iniciacao_com_mesmo_titulo_usa_o_trabalho_com_resumo():
    catalogo = {"c1": {"id": "c1", "titulo": "ESTUDO DE ROBÓTICA MÓVEL", "resumo": "R", "ano": 2023}}
    perfil, _, trabalhos = _perfil_com_iniciacoes([_ic("Estudo de robotica movel.", 2023)], catalogo)
    assert perfil["trabalhosIniciacaoCientifica"] == ["c1"]
    assert trabalhos["c1"]["resumo"] == "R"


def test_iniciacao_com_pequena_variacao_casa_mas_titulo_diferente_nao():
    catalogo = {"c1": {"id": "c1", "titulo": "Multiplicadores binários em microarquitetura RISC-V", "resumo": "R"}}
    perfil, _, _ = _perfil_com_iniciacoes([_ic("Multiplicadores binários em arquitetura RISC-V")], catalogo)
    assert perfil["trabalhosIniciacaoCientifica"] == ["c1"]
    perfil, _, trabalhos = _perfil_com_iniciacoes([_ic("Controle de drones agrícolas")], catalogo)
    assert trabalhos[perfil["trabalhosIniciacaoCientifica"][0]]["resumo"] is None


def test_iniciacao_nao_duplica_trabalho_vindo_do_sigaa_nem_renovacao():
    catalogo = {"c1": {"id": "c1", "titulo": "Tema A", "resumo": "R", "ano": 2023}}
    perfil, _, _ = _perfil_com_iniciacoes([_ic("Tema A", 2023)], catalogo, ids_sigaa=["c1"])
    assert perfil["trabalhosIniciacaoCientifica"] == ["c1"]
    perfil, _, trabalhos = _perfil_com_iniciacoes([_ic("Tema B", 2021), _ic("Tema B", 2022)], {})
    assert len(perfil["trabalhosIniciacaoCientifica"]) == 1
    assert trabalhos[perfil["trabalhosIniciacaoCientifica"][0]]["ano"] == 2022


def test_mesma_iniciacao_em_dois_professores_gera_um_registro():
    trabalhos = {}
    a, _, _ = _perfil_com_iniciacoes([_ic("Tema C")], {}, trabalhos=trabalhos)
    b, _, _ = _perfil_com_iniciacoes([_ic("Tema C")], {}, trabalhos=trabalhos)
    assert a["trabalhosIniciacaoCientifica"] == b["trabalhosIniciacaoCientifica"]
    assert len(trabalhos) == 1


def test_remover_duplicatas_ignora_caixa_acento_e_pontuacao():
    catalogo = {
        "a": {"id": "a", "titulo": "Análise de FPGA.", "tipo": "tcc", "ano_inicio": 2021},
        "b": {"id": "b", "titulo": "ANALISE DE FPGA", "tipo": "tcc", "ano_inicio": 2022},
    }
    assert g.remover_duplicatas(catalogo) == {"a": "b"}
    assert list(catalogo) == ["b"]


def test_remover_duplicatas_mantem_mais_texto_e_ano_mais_recente():
    catalogo = {
        "a": {"id": "a", "nome": "Projeto X", "descricao": "Descrição longa", "ano_conclusao": 2023},
        "b": {"id": "b", "nome": "Projeto X", "descricao": None, "ano_conclusao": 2026},
    }
    assert g.remover_duplicatas(catalogo, "nome") == {"b": "a"}
    assert catalogo["a"]["ano_conclusao"] == 2026


def test_remover_duplicatas_nao_une_titulos_parecidos_nem_vazios():
    catalogo = {
        "a": {"id": "a", "titulo": "VOT2016 challenge results"},
        "b": {"id": "b", "titulo": "VOT2017 challenge results"},
        "c": {"id": "c", "titulo": ""},
        "d": {"id": "d", "titulo": ""},
    }
    assert g.remover_duplicatas(catalogo) == {}
    assert len(catalogo) == 4


def test_deduplicar_catalogos_atualiza_referencias_sem_repetir_id():
    catalogo = {
        "a": {"id": "a", "titulo": "Tema", "ano": 2020},
        "b": {"id": "b", "titulo": "tema", "ano": 2021},
    }
    perfis = [{"producoes": ["a", "b"]}, {"producoes": ["a"]}]
    assert g.deduplicar_catalogos(perfis, {"producoes": (catalogo, "titulo")}) == {"producoes": 1}
    assert perfis == [{"producoes": ["b"]}, {"producoes": ["b"]}]


def test_titulos_equivalentes_aceita_subtitulo_so_em_titulo_longo():
    assert g.titulos_equivalentes("sixth visual object tracking challenge", "sixth visual object tracking challenge results")
    assert not g.titulos_equivalentes("robotica", "robotica movel")
    assert not g.titulos_equivalentes("", "")


def test_deduplicar_perfil_remove_repeticao_entre_secoes():
    catalogos = {
        "trabalhosIniciacaoCientifica": {"ic": {"titulo": "Balança IoT com LoRa", "resumo": "R"}},
        "producoes": {
            "p1": {"titulo": "BALANÇA IOT COM LORA"},
            "p2": {"titulo": "Programação de Sistemas Embarcados Desenvolvendo Software"},
            "p3": {"titulo": "Programação de Sistemas Embarcados"},
        },
        "orientacoes": {"o1": {"titulo": "Programação de Sistemas Embarcados: Desenvolvendo Software para C"}},
    }
    perfil = {"trabalhosIniciacaoCientifica": ["ic"], "producoes": ["p1", "p2", "p3"], "orientacoes": ["o1"]}
    removidos = g.deduplicar_perfil(perfil, catalogos)
    assert perfil["trabalhosIniciacaoCientifica"] == ["ic"]
    # p3 tem só 4 palavras: curto demais para ser tratado como p2 sem subtítulo.
    assert perfil["producoes"] == ["p2", "p3"]
    assert perfil["orientacoes"] == []
    assert removidos["producoes"] == 1 and removidos["orientacoes"] == 1
    assert g.titulos_repetidos(perfil, catalogos) == []


def test_deduplicar_perfil_une_disciplinas_por_nome_e_por_ementa():
    ementa = "Arquitetura de microcontroladores, periféricos, interrupções e programação em C."
    catalogos = {
        "disciplinas": {
            "1": {"nome": "Antenas e Propagação", "ementa": None},
            "2": {"nome": "ANTENAS E PROPAGAÇÃO", "ementa": "Parâmetros de antenas."},
            "3": {"nome": "Microcontroladores", "ementa": ementa},
            "4": {"nome": "Microcontroladores (Prática)", "ementa": ementa.lower()},
            "5": {"nome": "Robótica", "ementa": "Cinemática de manipuladores."},
        }
    }
    perfil = {"disciplinas": ["1", "2", "3", "4", "5"]}
    g.deduplicar_perfil(perfil, catalogos)
    # A lista vem da mais recente para a mais antiga: fica a primeira de cada grupo.
    assert perfil["disciplinas"] == ["1", "3", "5"]


def test_deduplicar_perfil_mantem_referencia_orfa():
    perfil = {"producoes": ["sem_catalogo"]}
    g.deduplicar_perfil(perfil, {"producoes": {}})
    assert perfil["producoes"] == ["sem_catalogo"]


def test_remover_nao_referenciados():
    catalogo = {"a": {}, "b": {}}
    g.remover_nao_referenciados([{"producoes": ["a"]}], {"producoes": catalogo})
    assert list(catalogo) == ["a"]


def test_ementas_curtas_de_modelo_nao_unem_materias_diferentes():
    modelo = "experiencias de laboratorio sobre temas abordados na disciplina "
    assert not g.ementas_parecidas(modelo + "instrumentacao industrial i", modelo + "redes industriais de comunicacao")
    assert g.ementas_parecidas(modelo + "instrumentacao industrial i", modelo + "instrumentacao industrial i")


def test_deduplicar_perfil_mantem_disciplina_mais_recente_mesmo_com_menos_texto():
    catalogos = {
        "disciplinas": {
            "nova": {"nome": "Robótica", "ementa": None},
            "antiga": {"nome": "ROBÓTICA", "ementa": "Cinemática de manipuladores."},
        }
    }
    perfil = {"disciplinas": ["nova", "antiga"]}
    g.deduplicar_perfil(perfil, catalogos)
    assert perfil["disciplinas"] == ["nova"]


def test_disciplina_mais_recente_sem_ementa_recebe_a_da_versao_antiga():
    catalogos = {
        "disciplinas": {
            "nova": {"nome": "Robótica", "ementa": "."},
            "antiga": {"nome": "ROBÓTICA", "ementa": "Cinemática de manipuladores."},
            "outra": {"nome": "Redes", "ementa": None},
        }
    }
    perfil = {"disciplinas": ["nova", "outra", "antiga"]}
    g.deduplicar_perfil(perfil, catalogos)
    assert perfil["disciplinas"] == ["nova", "outra"]
    assert catalogos["disciplinas"]["nova"]["ementa"] == "Cinemática de manipuladores."
    assert catalogos["disciplinas"]["outra"]["ementa"] is None


def test_versao_de_mesmo_nome_de_disciplina_removida_tambem_sai():
    ementa = "Programação orientada a objetos: classes, herança, polimorfismo e interfaces."
    catalogos = {
        "disciplinas": {
            "teoria": {"nome": "POO", "ementa": ementa},
            "pratica_nova": {"nome": "POO (Prática)", "ementa": ementa},
            "pratica_antiga": {"nome": "POO (PRÁTICA)", "ementa": None},
        }
    }
    perfil = {"disciplinas": ["teoria", "pratica_nova", "pratica_antiga"]}
    g.deduplicar_perfil(perfil, catalogos)
    assert perfil["disciplinas"] == ["teoria"]
