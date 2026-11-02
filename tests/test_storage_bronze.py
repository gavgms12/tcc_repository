import pytest

from storage import minio_storage as ms


def test_chave_datada_coloca_data_na_pasta_e_no_arquivo():
    assert (
        ms.chave_datada("raw/sigaa/professores_sigaa.json", "20261015")
        == "raw/20261015/sigaa/professores_sigaa_20261015.json"
    )


def test_chave_datada_sem_subpasta_e_com_lattes():
    assert ms.chave_datada("raw/x.json", "20261015") == "raw/20261015/x_20261015.json"
    assert (
        ms.chave_datada("raw/lattes/json/1234567890123456.json", "20261015")
        == "raw/20261015/lattes/json/1234567890123456_20261015.json"
    )


def test_chave_datada_exige_prefixo_raw():
    with pytest.raises(ValueError):
        ms.chave_datada("silver/x.parquet", "20261015")


def test_chave_logica_de_e_inverso_de_chave_datada():
    real = ms.chave_datada("raw/sigaa/docentes_sigaa.json", "20261015")
    assert ms.chave_logica_de(real) == ("raw/sigaa/docentes_sigaa.json", "20261015")


def test_chave_logica_de_ignora_chave_sem_data():
    assert ms.chave_logica_de("raw/sigaa/docentes_sigaa.json") is None
    # datas divergentes entre pasta e arquivo não são uma chave datada válida
    assert ms.chave_logica_de("raw/20261015/a/x_20261016.json") is None


def test_leitura_recente_le_so_a_pasta_de_data_mais_nova(s3):
    ms.salvar_json_bronze_datado("raw/sigaa/p.json", {"v": 1}, data="20261001")
    ms.salvar_json_bronze_datado("raw/sigaa/p.json", {"v": 2}, data="20261015")
    assert ms.data_bronze_leitura() == "20261015"
    assert ms.ler_json_bronze_recente("raw/sigaa/p.json") == {"v": 2}


def test_coletas_antigas_sao_preservadas(s3):
    ms.salvar_json_bronze_datado("raw/sigaa/p.json", {"v": 1}, data="20261001")
    ms.salvar_json_bronze_datado("raw/sigaa/p.json", {"v": 2}, data="20261015")
    chaves = ms.BRONZE.listar("raw/")
    assert "raw/20261001/sigaa/p_20261001.json" in chaves
    assert "raw/20261015/sigaa/p_20261015.json" in chaves


def test_leitura_nao_recorre_a_data_antiga_quando_falta_na_mais_nova(s3):
    ms.salvar_json_bronze_datado("raw/sigaa/p.json", {"v": 1}, data="20261001")
    ms.salvar_json_bronze_datado("raw/outra/x.json", {"x": 1}, data="20261015")
    with pytest.raises(FileNotFoundError, match="20261015"):
        ms.ler_json_bronze_recente("raw/sigaa/p.json")


def test_data_pode_ser_fixada_por_variavel_de_ambiente(s3, monkeypatch):
    ms.salvar_json_bronze_datado("raw/sigaa/p.json", {"v": 1}, data="20261001")
    ms.salvar_json_bronze_datado("raw/sigaa/p.json", {"v": 2}, data="20261015")
    monkeypatch.setenv("BRONZE_DATA", "20261001")
    assert ms.ler_json_bronze_recente("raw/sigaa/p.json") == {"v": 1}


def test_curriculos_listados_so_da_pasta_mais_recente(s3):
    ms.salvar_json_bronze_datado("raw/lattes/json/A.json", {"id": "A"}, data="20261001")
    ms.salvar_json_bronze_datado("raw/lattes/json/B.json", {"id": "B"}, data="20261001")
    ms.salvar_json_bronze_datado("raw/lattes/json/A.json", {"id": "A2"}, data="20261015")
    recentes = ms.chaves_bronze_da_data("raw/lattes/json/")
    assert recentes == {"raw/lattes/json/A.json": "raw/20261015/lattes/json/A_20261015.json"}


def test_ultima_versao_procura_em_datas_anteriores(s3):
    ms.salvar_json_bronze_datado("raw/sigaa/p.json", {"v": 1}, data="20261001")
    ms.salvar_json_bronze_datado("raw/outra/x.json", {"x": 1}, data="20261015")
    assert ms.ler_json_bronze_ultima_versao("raw/sigaa/p.json") == {"v": 1}


def test_sem_nenhuma_versao_levanta(s3):
    ms.salvar_json_bronze_datado("raw/outra/x.json", {"x": 1}, data="20261015")
    with pytest.raises(FileNotFoundError):
        ms.ler_json_bronze_ultima_versao("raw/nao/existe.json")
    assert ms.ler_json_bronze_ultima_versao_ou_none("raw/nao/existe.json") is None


def test_bronze_vazia_nao_tem_data_de_leitura(s3):
    with pytest.raises(FileNotFoundError):
        ms.data_bronze_leitura()


def test_data_coleta_usa_fuso_do_brasil_e_nao_utc(monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.delenv("DATA_COLETA", raising=False)

    class Relogio(datetime):
        @classmethod
        def now(cls, tz=None):
            # 01:38 UTC de 16/10 == 22:38 de 15/10 em Brasília
            return datetime(2026, 10, 16, 1, 38, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(ms, "datetime", Relogio)
    assert ms.data_coleta() == "20261015"
    monkeypatch.setenv("TZ_COLETA", "UTC")
    assert ms.data_coleta() == "20261016"
