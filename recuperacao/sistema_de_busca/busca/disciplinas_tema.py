"""Disciplinas do tema: o campo "disciplinas" de cada tópico em config.TOPICOS.

Quem leciona uma disciplina listada no tema é evidência direta (não depende do modelo):
  - a disciplina entra sempre como candidata do professor e não é cortada;
  - o professor ganha um bônus no score do tópico (config.BONUS_DISCIPLINA_TEMA);
  - opcionalmente, o professor entra no ranking mesmo fora dos melhores da busca.

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
                with_payload=["id", "nome", "codigo", "professor_ids", "texto"], with_vectors=False,
            )
            payloads += [p.payload for p in pontos]
            if offset is None:
                break
        _catalogo[id(client)] = payloads
    return _catalogo[id(client)]


def disciplinas_do_topico(client, topico: str) -> list[dict]:
    """Disciplinas (payloads) cujo nome está na lista "disciplinas" do tópico. Vazio para texto livre."""
    nomes = {normalizar_nome(n) for n in config.disciplinas_topico(topico)}
    if not nomes:
        return []
    return [d for d in catalogo_disciplinas(client) if normalizar_nome(d.get("nome")) in nomes]


def professores_do_topico(client, topico: str) -> set[str]:
    """Professores que lecionam alguma disciplina do tópico."""
    return {str(pid) for d in disciplinas_do_topico(client, topico) for pid in d.get("professor_ids") or []}


def bonus(qtd_disciplinas: int) -> float:
    """Bônus no score do tópico por quantidade de disciplinas do tema (nomes distintos) que o professor leciona."""
    return min(config.BONUS_DISCIPLINA_TEMA * qtd_disciplinas, config.BONUS_DISCIPLINA_TEMA_MAX)
