from common.lattes import id_lattes_valido, validar_id_lattes
from common.texto import normalizar_nome, normalizar_texto


def test_normalizar_texto():
    assert normalizar_texto("  a \n  b\t c ") == "a b c"
    assert normalizar_texto(None) == ""


def test_normalizar_nome_remove_acentos_e_poe_em_maiusculas():
    assert normalizar_nome("  José   da Conceição ") == "JOSE DA CONCEICAO"


def test_validar_id_lattes():
    assert validar_id_lattes("http://lattes.cnpq.br/2146410092995682") == "2146410092995682"
    assert validar_id_lattes("http://lattes.cnpq.br/123") is None
    assert validar_id_lattes(None) is None
    assert id_lattes_valido("2146410092995682")
    assert not id_lattes_valido("21464100929956AB")
