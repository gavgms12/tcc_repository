import math

import pytest

from recuperacao.sistema_de_busca.avaliacao.metricas import hit_at_k, mrr, ndcg_at_k, recall_at_k


def test_relevante_em_primeiro():
    r, rel = ["a", "b", "c"], {"a": 1}
    assert ndcg_at_k(r, rel) == pytest.approx(1.0)
    assert mrr(r, rel) == 1.0
    assert recall_at_k(r, rel) == 1.0
    assert hit_at_k(r, rel) == 1.0


def test_relevante_em_terceiro():
    r, rel = ["x", "y", "a", "z"], {"a": 1}
    assert ndcg_at_k(r, rel) == pytest.approx(1 / math.log2(4))
    assert mrr(r, rel) == pytest.approx(1 / 3)
    assert recall_at_k(r, rel, 5) == 1.0
    assert recall_at_k(r, rel, 2) == 0.0
    assert hit_at_k(r, rel) == 0.0


def test_relevante_ausente():
    r, rel = ["x", "y"], {"a": 1}
    assert ndcg_at_k(r, rel) == 0.0
    assert mrr(r, rel) == 0.0
    assert recall_at_k(r, rel) == 0.0


def test_dois_orientadores_recall_parcial():
    assert recall_at_k(["a", "x", "y"], {"a": 1, "b": 1}, 3) == 0.5


def test_sem_relevantes():
    assert ndcg_at_k(["a"], {}) == 0.0
    assert recall_at_k(["a"], {}) == 0.0
