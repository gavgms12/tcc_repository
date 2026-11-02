from common.texto import dividir_frases
from silver.integracao.resumo import separar_resumo


def test_titulacao_vai_para_campo_proprio_e_conteudo_fica():
    r = separar_resumo(
        "Possui graduação em Engenharia pela UNIFEI (2001). "
        "Tem experiência em redes, atuando em IoT."
    )
    assert r["essencial"] == "Tem experiência em redes, atuando em IoT"
    assert r["titulacao"] == "Possui graduação em Engenharia pela UNIFEI (2001)."


def test_frase_de_titulacao_com_conteudo_nao_e_removida():
    texto = "Doutor em Engenharia Elétrica com ênfase em Automação"
    assert separar_resumo(texto) == {"essencial": texto, "titulacao": None}


def test_cargo_sem_conteudo_sai_e_com_conteudo_fica():
    assert separar_resumo("Atualmente é professor associado da UNIFEI.")["essencial"] is None
    texto = "Professor na área de computação"
    assert separar_resumo(texto)["essencial"] == texto


def test_remove_traducao_marcador_e_repeticao():
    r = separar_resumo("Português: Atua em redes. Atua em redes. English: He works on networks.")
    assert r["essencial"] == "Atua em redes"


def test_frase_que_cita_titulo_mas_descreve_atuacao_fica():
    texto = "Durante o mestrado, aprofundei meus estudos em confiabilidade de sistemas"
    assert separar_resumo(texto) == {"essencial": texto, "titulacao": None}


def test_nome_de_instituicao_nao_conta_como_conteudo():
    texto = "Possui graduação em Matemática pela Fundação de Ensino e Pesquisa (1996)."
    assert separar_resumo(texto) == {"essencial": None, "titulacao": texto}


def test_cargo_historico_nao_e_removido():
    texto = "De 2015 a 2021, trabalhou como pesquisador no Inatel"
    assert separar_resumo(texto)["essencial"] == texto


def test_possui_sem_titulo_nao_e_titulacao():
    texto = "Possui experiência em docência e em antenas. Possui interesses em sinais."
    assert separar_resumo(texto)["titulacao"] is None
    assert separar_resumo(texto)["essencial"] == texto.rstrip(".")


def test_vazio():
    assert separar_resumo(None) == {"essencial": None, "titulacao": None}


def test_dividir_frases_corrige_ponto_colado_e_preserva_iniciais():
    assert dividir_frases("Na UNIFEI.Tem foco. Pela E. E. Técnico Neves.") == [
        "Na UNIFEI.", "Tem foco.", "Pela E. E. Técnico Neves.",
    ]
