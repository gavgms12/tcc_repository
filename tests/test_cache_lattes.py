import os
import time

from silver.integracao.executar_scriptlattes import expirar_cache


def _arquivo(pasta, nome, idade_dias, agora):
    caminho = pasta / nome
    caminho.write_text("cv")
    antigo = agora - idade_dias * 86400
    os.utime(caminho, (antigo, antigo))
    return caminho


def test_remove_so_o_que_passou_da_validade(tmp_path):
    agora = time.time()
    _arquivo(tmp_path, "velho", 40, agora)
    _arquivo(tmp_path, "novo", 5, agora)
    assert expirar_cache(tmp_path, validade_dias=30, agora=agora) == ["velho"]
    assert [p.name for p in tmp_path.iterdir()] == ["novo"]


def test_validade_zero_desativa_a_expiracao(tmp_path):
    agora = time.time()
    _arquivo(tmp_path, "velho", 400, agora)
    assert expirar_cache(tmp_path, validade_dias=0, agora=agora) == []
    assert (tmp_path / "velho").exists()


def test_diretorio_inexistente_nao_falha(tmp_path):
    assert expirar_cache(tmp_path / "nao_existe", validade_dias=30) == []


def test_curriculos_sao_gravados_na_data_da_coleta_lida_e_nao_na_de_hoje(s3, tmp_path):
    import json

    from silver.integracao.executar_scriptlattes import enviar_jsons
    from storage import minio_storage as ms

    (tmp_path / "2146410092995682.json").write_text(json.dumps({"id": 1}))
    assert enviar_jsons(tmp_path, "raw/lattes/json", data="20261015") == 1
    assert ms.BRONZE.existe("raw/20261015/lattes/json/2146410092995682_20261015.json")
    assert not ms.BRONZE.listar("raw/20261016/")
