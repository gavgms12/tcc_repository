"""Cache em disco (SQLite) das notas do reranker.

A chave é um hash de (modelo, max_length, consulta, texto do item). Se qualquer um mudar
(ementa do tópico, texto do item reindexado, outro modelo), a chave muda e o par é recalculado:
nunca se usa uma nota velha por engano.
"""
import hashlib
import sqlite3
from pathlib import Path

from recuperacao.sistema_de_busca import config


def chave(consulta: str, texto: str, max_length: int) -> str:
    bruto = f"{config.RERANKER_MODEL}\x00{max_length}\x00{consulta}\x00{texto}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


class CacheRerank:
    def __init__(self, caminho: str | Path | None = None):
        self.caminho = Path(caminho or config.RERANK_CACHE_PATH)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: a API usa o cache em threads diferentes (uma requisição por vez, ver api.py)
        self.con = sqlite3.connect(self.caminho, check_same_thread=False)
        self.con.execute("CREATE TABLE IF NOT EXISTS scores (chave TEXT PRIMARY KEY, score REAL NOT NULL)")
        self.con.commit()

    def buscar(self, chaves: list[str]) -> dict[str, float]:
        encontrados: dict[str, float] = {}
        for i in range(0, len(chaves), 500):
            parte = chaves[i:i + 500]
            marcadores = ",".join("?" * len(parte))
            for k, s in self.con.execute(f"SELECT chave, score FROM scores WHERE chave IN ({marcadores})", parte):
                encontrados[k] = s
        return encontrados

    def salvar(self, itens: dict[str, float]) -> None:
        self.con.executemany("INSERT OR REPLACE INTO scores (chave, score) VALUES (?, ?)", itens.items())
        self.con.commit()

    def __len__(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM scores").fetchone()[0]


_instancia: CacheRerank | None = None


def cache_disco() -> CacheRerank | None:
    """Cache compartilhado; None se config.RERANK_CACHE_PATH estiver desligado."""
    global _instancia
    if not config.RERANK_CACHE_PATH:
        return None
    if _instancia is None:
        _instancia = CacheRerank()
    return _instancia
