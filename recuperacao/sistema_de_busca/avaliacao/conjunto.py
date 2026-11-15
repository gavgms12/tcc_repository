"""Conjuntos de referência: trabalho orientado -> orientador(es).

- "tcc": título de cada TCC (coleção de orientações).
- "ic:titulo" e "ic:titulo+palavras": cada iniciação científica (coleção de ICs), só pelo título ou pelo
  título + palavras-chave (o resumo fica de fora: seria quebrado em dezenas de consultas pelo reranker e
  ocuparia o limite de 512 tokens).

O texto vira uma consulta de texto livre (como na API). Para não vazar a resposta, cada consulta guarda em
"excluir" o próprio trabalho e todo item, de qualquer coleção, com o mesmo título (a IC, o artigo ou o projeto do
mesmo trabalho); o Recomendador ignora esses ids na busca (Recomendador.excluir).
"""
import json
import random
import re
import unicodedata
from pathlib import Path

from recuperacao.sistema_de_busca import config

NOME_TEXTO_LIVRE = "Texto livre"   # mesmo nome que a API usa para o texto do aluno


def normalizar(texto) -> str:
    """Minúsculo, sem acentos e sem pontuação (para casar títulos)."""
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _scroll(client, colecao: str, campos: list[str]) -> list[dict]:
    if not client.collection_exists(colecao):
        return []
    payloads, offset = [], None
    while True:
        pontos, offset = client.scroll(colecao, limit=500, offset=offset, with_payload=campos, with_vectors=False)
        payloads += [p.payload for p in pontos]
        if offset is None:
            return payloads


def ids_por_titulo(client) -> dict[str, dict[str, set[str]]]:
    """{título normalizado: {tipo: ids}} de todas as coleções de itens."""
    indice: dict[str, dict[str, set[str]]] = {}
    for tipo, cfg in config.FONTES_ITENS.items():
        for p in _scroll(client, cfg["collection"], ["id", "titulo", "nome"]):
            titulo = normalizar(p.get("titulo") or p.get("nome"))
            if titulo:
                indice.setdefault(titulo, {}).setdefault(tipo, set()).add(str(p["id"]))
    return indice


def consultas_tcc(client, n: int | None = None, anos: tuple[int, int] | None = None,
                  semente: int = 42) -> list[dict]:
    """Amostra de TCCs (semente fixa: as mesmas consultas em todas as configurações e rodadas)."""
    tccs = [
        p for p in _scroll(client, config.COLLECTION_ORIENTADOR, ["id", "titulo", "tipo", "ano", "professor_ids"])
        if p.get("tipo") == "tcc" and p.get("titulo") and p.get("professor_ids")
        and (anos is None or (p.get("ano") is not None and anos[0] <= p["ano"] <= anos[1]))
    ]
    tccs.sort(key=lambda p: str(p["id"]))
    if n is not None and n < len(tccs):
        tccs = random.Random(semente).sample(tccs, n)

    indice = ids_por_titulo(client)
    consultas = []
    for p in tccs:
        excluir = {tipo: set(ids) for tipo, ids in indice.get(normalizar(p["titulo"]), {}).items()}
        excluir.setdefault("orientacao", set()).add(str(p["id"]))
        consultas.append({
            "conjunto": "tcc",
            "id": str(p["id"]),
            "titulo": p["titulo"],
            "ano": p.get("ano"),
            "topicos": {NOME_TEXTO_LIVRE: p["titulo"].strip().lower()},   # igual à API
            "relevantes": {str(pid): 1 for pid in p["professor_ids"]},
            "excluir": excluir,
        })
    return consultas


CONSULTAS_IC = ("titulo", "titulo+palavras")


def _palavras_chave(texto: str) -> str:
    """Linha "Palavras-chave: ..." do texto indexado da IC (ver textos.ics_montar_texto_para_modelo)."""
    for linha in str(texto or "").splitlines():
        if linha.lower().startswith("palavras-chave:"):
            return linha.split(":", 1)[1].strip()
    return ""


def consultas_ic(client, consulta: str = "titulo", n: int | None = None, semente: int = 42) -> list[dict]:
    """ICs no formato de consulta. consulta: "titulo" ou "titulo+palavras" (sem palavras-chave, usa só o título)."""
    if consulta not in CONSULTAS_IC:
        raise ValueError(f"consulta inválida: {consulta!r} (use {CONSULTAS_IC})")
    ics = [p for p in _scroll(client, config.COLLECTION_ICS, ["id", "titulo", "texto", "ano", "professor_ids"])
           if p.get("titulo") and p.get("professor_ids")]
    ics.sort(key=lambda p: str(p["id"]))
    if n is not None and n < len(ics):
        ics = random.Random(semente).sample(ics, n)

    indice = ids_por_titulo(client)
    consultas = []
    for p in ics:
        texto = p["titulo"].strip()
        palavras = _palavras_chave(p.get("texto"))
        if consulta == "titulo+palavras" and palavras:
            texto = f"{texto}. {palavras}"
        excluir = {tipo: set(ids) for tipo, ids in indice.get(normalizar(p["titulo"]), {}).items()}
        excluir.setdefault("trabalho", set()).add(str(p["id"]))
        consultas.append({
            "conjunto": f"ic:{consulta}",
            "id": str(p["id"]),
            "titulo": texto,
            "ano": p.get("ano"),
            "topicos": {NOME_TEXTO_LIVRE: texto.lower()},
            "relevantes": {str(pid): 1 for pid in p["professor_ids"]},
            "excluir": excluir,
        })
    return consultas


# ---------------------------------------------------------------------------
# Consultas escritas à mão
# ---------------------------------------------------------------------------
ARQUIVO_MANUAL = Path(__file__).resolve().parent / "consultas_manuais.json"
GANHO = {"alta": 2, "media": 1}


def professores_por_nome(client) -> dict[str, str]:
    """{nome normalizado: SIAPE} dos professores com perfil indexado."""
    return {normalizar(p.get("nome")): str(p["id"])
            for p in _scroll(client, config.COLLECTION_PROFESSORES, ["id", "nome"]) if p.get("nome")}


def consultas_manuais(client, caminho: Path = ARQUIVO_MANUAL) -> list[dict]:
    """Consultas do arquivo JSON: cada uma com "texto" e/ou "temas" (como no questionário) e os professores
    esperados em "alta" (as melhores escolhas, ganho 2) e "media" (também serviriam, ganho 1)."""
    if not caminho.exists():
        raise SystemExit(f"{caminho} não existe. Gere o modelo com --gerar-modelo e preencha.")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    siape = professores_por_nome(client)
    consultas = []
    for i, c in enumerate(dados.get("consultas", []), start=1):
        topicos = {}
        for tema in c.get("temas") or []:
            if tema not in config.TOPICOS:
                print(f"  aviso: consulta {i}: tema desconhecido {tema!r} (ignorado)")
                continue
            topicos[tema] = config.texto_topico(tema)
        texto = (c.get("texto") or "").strip()
        if texto:
            topicos[NOME_TEXTO_LIVRE] = texto.lower()   # igual à API
        relevantes = {}
        for nivel, ganho in GANHO.items():
            for nome in c.get(nivel) or []:
                pid = siape.get(normalizar(nome))
                if pid is None:
                    print(f"  aviso: consulta {i}: professor não encontrado {nome!r} (ignorado)")
                    continue
                relevantes[pid] = max(relevantes.get(pid, 0), ganho)
        if not topicos or not relevantes:
            print(f"  aviso: consulta {i} sem texto/temas ou sem professores esperados (ignorada)")
            continue
        consultas.append({
            "conjunto": "manual",
            "id": str(c.get("id") or i),
            "titulo": texto or " + ".join(topicos),
            "ano": None,
            "topicos": topicos,
            "relevantes": relevantes,
            "excluir": {},
        })
    return consultas


def gerar_modelo_manual(client, caminho: Path = ARQUIVO_MANUAL) -> None:
    """Cria o JSON de exemplo, com a lista de professores e de temas para consulta."""
    if caminho.exists():
        raise SystemExit(f"{caminho} já existe; edite o arquivo atual ou apague-o para gerar de novo.")
    nomes = sorted(p["nome"] for p in _scroll(client, config.COLLECTION_PROFESSORES, ["nome"]) if p.get("nome"))
    modelo = {
        "_instrucoes": ("Cada consulta tem 'texto' (o que o aluno escreveria) e/ou 'temas' (nomes de '_temas'), "
                        "e os professores esperados em 'alta' (melhores escolhas) e 'media' (também serviriam), "
                        "com os nomes de '_professores'. 'id' é opcional."),
        "_temas": list(config.TOPICOS),
        "_professores": nomes,
        "consultas": [
            {"id": "exemplo-1", "texto": "quero usar visão computacional para monitorar plantações",
             "temas": [], "alta": [], "media": []},
            {"id": "exemplo-2", "texto": "", "temas": ["Sistemas Embarcados", "Internet das Coisas"],
             "alta": [], "media": []},
        ],
    }
    caminho.write_text(json.dumps(modelo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Modelo criado em {caminho}")
