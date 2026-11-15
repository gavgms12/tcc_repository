"""Métricas de ranking para a avaliação offline.

ranking:     lista de professor_id na ordem devolvida pelo sistema
relevantes:  {professor_id: ganho}; ganho > 0 é relevante (TCC: 1 para cada orientador)
"""
import math


def _dcg(ganhos: list[float]) -> float:
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ganhos))


def ndcg_at_k(ranking: list[str], relevantes: dict[str, float], k: int = 5) -> float:
    """DCG dos k primeiros dividido pelo DCG do ranking ideal (1 = relevantes no topo)."""
    ideal = _dcg(sorted((g for g in relevantes.values() if g > 0), reverse=True)[:k])
    if not ideal:
        return 0.0
    return _dcg([relevantes.get(pid, 0) for pid in ranking[:k]]) / ideal


def mrr(ranking: list[str], relevantes: dict[str, float]) -> float:
    """1 / posição do primeiro relevante na lista inteira (0 se nenhum aparece)."""
    for i, pid in enumerate(ranking, start=1):
        if relevantes.get(pid, 0) > 0:
            return 1.0 / i
    return 0.0


def recall_at_k(ranking: list[str], relevantes: dict[str, float], k: int = 5) -> float:
    """Fração dos relevantes que aparecem nos k primeiros."""
    alvo = {pid for pid, g in relevantes.items() if g > 0}
    if not alvo:
        return 0.0
    return len(alvo & set(ranking[:k])) / len(alvo)


def hit_at_k(ranking: list[str], relevantes: dict[str, float], k: int = 1) -> float:
    """1 se algum relevante aparece nos k primeiros, senão 0."""
    return float(any(relevantes.get(pid, 0) > 0 for pid in ranking[:k]))


def nomes(k: int) -> list[str]:
    return [f"ndcg@{k}", "mrr", f"recall@{k}", "hit@1"]


def todas(ranking: list[str], relevantes: dict[str, float], k: int = 5) -> dict[str, float]:
    return dict(zip(nomes(k), (
        ndcg_at_k(ranking, relevantes, k),
        mrr(ranking, relevantes),
        recall_at_k(ranking, relevantes, k),
        hit_at_k(ranking, relevantes, 1),
    )))
