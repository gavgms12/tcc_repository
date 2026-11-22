"""Disciplinas do tema: o campo "disciplinas" de cada tópico em config.TOPICOS.

Quem leciona uma disciplina listada no tema é evidência direta (não depende do modelo):
  - a disciplina entra sempre como candidata do professor e não é cortada;
  - o professor ganha um bônus no score do tópico (config.BONUS_DISCIPLINA_TEMA).

O casamento é pelo nome, ignorando acentos, maiúsculas, pontuação e um código no início
("SD122 Circuitos Digitais I" casa com "Circuitos Digitais I"). Um mesmo nome pode ter vários
códigos (versões da disciplina): todos contam, mas o bônus conta o nome uma vez só.
"""
import re
import unicodedata

from recuperacao.sistema_de_busca import config

_CODIGO_NO_INICIO = re.compile(r"^[a-z]{1,6}\d+[a-z0-9]*\s+")
_catalogo: dict[int, list[dict]] = {}


def normalizar_nome(nome) -> str:
    """Minúsculo, sem acentos, sem pontuação e sem código no início."""
    texto = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode().lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto).strip()
    return _CODIGO_NO_INICIO.sub("", texto)


def catalogo_disciplinas(client) -> list[dict]:
    """Payload de todas as disciplinas (lido uma vez por client; são poucas centenas)."""
    if id(client) not in _catalogo:
        payloads, offset = [], None
        while True:
            pontos, offset = client.scroll(
                config.COLLECTION_DISCIPLINAS, limit=500, offset=offset,
                with_payload=["id", "nome", "codigo", "professor_ids", "anos_professores", "texto"],
                with_vectors=False,
            )
            payloads += [p.payload for p in pontos]
            if offset is None:
                break
        _catalogo[id(client)] = payloads
    return _catalogo[id(client)]


def ano_min_disciplinas(ano_min=None, piso=None):
    """Ano inicial das disciplinas: o do aluno, mas nunca antes de config.ANO_MINIMO_DISCIPLINAS."""
    piso = config.ANO_MINIMO_DISCIPLINAS if piso is None else piso
    if piso is None:
        return ano_min
    return piso if ano_min is None else max(ano_min, piso)


def professores_no_periodo(payload: dict, ano_min=None, ano_max=None) -> list:
    """`professor_ids` da disciplina, só com quem a lecionou em algum ano entre ano_min e ano_max.

    Sem filtro de ano, ou sem "anos_professores" no payload (índice antigo), não corta ninguém.
    """
    ids = payload.get("professor_ids") or []
    anos = payload.get("anos_professores")
    if (ano_min is None and ano_max is None) or anos is None:
        return ids
    return [
        pid for pid in ids
        if any((ano_min is None or a >= ano_min) and (ano_max is None or a <= ano_max)
               for a in anos.get(str(pid), ()))
    ]


def restringir_ao_periodo(pontos, ano_min=None, ano_max=None):
    """Corta de cada ponto de disciplina os professores que não a lecionaram no período (altera o payload)."""
    for p in pontos:
        p.payload["professor_ids"] = professores_no_periodo(p.payload, ano_min, ano_max)
    return pontos


def disciplinas_do_topico(client, topico: str, ano_min=None, ano_max=None) -> list[dict]:
    """Disciplinas (payloads) cujo nome está na lista "disciplinas" do tópico. Vazio para texto livre.

    Com filtro de ano, cada disciplina só fica com os professores que a lecionaram no período.
    """
    nomes = {normalizar_nome(n) for n in config.disciplinas_topico(topico)}
    if not nomes:
        return []
    return [
        d | {"professor_ids": professores_no_periodo(d, ano_min, ano_max)}
        for d in catalogo_disciplinas(client) if normalizar_nome(d.get("nome")) in nomes
    ]


def bonus(qtd_disciplinas: int) -> float:
    """Bônus no score do tópico por quantidade de disciplinas do tema (nomes distintos) que o professor leciona."""
    return min(config.BONUS_DISCIPLINA_TEMA * qtd_disciplinas, config.BONUS_DISCIPLINA_TEMA_MAX)
