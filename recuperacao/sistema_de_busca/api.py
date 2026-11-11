"""API HTTP da busca de orientadores: recebe um texto livre (ou tópicos do catálogo) e devolve o ranking em JSON.

Rodar localmente (carrega os modelos e sobe em http://localhost:8000, docs em /docs):
    venv\\Scripts\\python.exe -m recuperacao.sistema_de_busca.api

No Colab (GPU + link público): ver recuperacao/colab_api_busca.ipynb
"""
import threading
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from recuperacao.sistema_de_busca import config
from recuperacao.sistema_de_busca.busca.exibicao import _melhores_itens, resumo_perfil

NOME_TEXTO_LIVRE = "Texto livre"
PASTA_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"   # recuperacao/frontend


class PedidoBusca(BaseModel):
    texto: str | None = Field(None, max_length=2000, description="Texto livre do aluno (ex.: o tema que quer pesquisar)")
    topicos: list[str] | None = Field(None, max_length=5, description="Nomes de tópicos do catálogo (GET /topicos)")
    top_k: int = Field(5, ge=1, le=50, description="Quantos professores devolver")
    n_itens: int = Field(3, ge=1, le=20, description="Quantos itens (evidências) por tipo em 'destaques'")
    ano_min: int | None = None
    ano_max: int | None = None
    incluir_pre_ranking: bool = Field(False, description="Também devolve o ranking antes do reranking")


def _limpar(valor):
    """Converte tipos do numpy/pandas para tipos do Python (JSON)."""
    if isinstance(valor, dict):
        return {str(k): _limpar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpar(v) for v in valor]
    if isinstance(valor, np.generic):
        valor = valor.item()
    if isinstance(valor, float) and valor != valor:   # NaN
        return None
    return valor


def _montar_topicos(pedido: PedidoBusca) -> dict[str, str]:
    topicos = {}
    for nome in pedido.topicos or []:
        if nome not in config.TOPICOS:
            raise HTTPException(422, f"Tópico desconhecido: {nome!r}. Veja GET /topicos.")
        topicos[nome] = config.texto_topico(nome)
    if pedido.texto and pedido.texto.strip():
        topicos[NOME_TEXTO_LIVRE] = pedido.texto.strip().lower()
    if not topicos:
        raise HTTPException(422, "Envie 'texto' e/ou 'topicos'.")
    return topicos


def criar_app(rec) -> FastAPI:
    """rec: Recomendador já com modelos carregados."""
    app = FastAPI(title="Busca de orientadores", version="1.0")
    # libera chamadas de front-ends em outro domínio (o link do Colab é diferente do site que exibe)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    # Uma busca por vez: o Recomendador guarda estado (tempos, caches) e o modelo ocupa a GPU inteira.
    trava = threading.Lock()

    @app.get("/saude")
    def saude():
        return {"ok": True}

    @app.get("/topicos")
    def topicos():
        detalhes = [
            {
                "nome": nome,
                "categoria": (dados.get("categoria") if isinstance(dados, dict) else None) or "Outros",
                "descricao": dados.get("descricao") if isinstance(dados, dict) else dados,
                "disciplinas": config.disciplinas_topico(nome),
            }
            for nome, dados in config.TOPICOS.items()
        ]
        return {"topicos": list(config.TOPICOS), "detalhes": detalhes}

    # front-end do questionário (recuperacao/frontend) no mesmo endereço da API
    if PASTA_FRONTEND.is_dir():
        app.mount("/app", StaticFiles(directory=PASTA_FRONTEND, html=True), name="frontend")

        @app.get("/", include_in_schema=False)
        def inicio():
            return RedirectResponse("/app/")

    @app.post("/recomendar")
    def recomendar(pedido: PedidoBusca):
        topicos = _montar_topicos(pedido)
        with trava:
            pre = None
            if pedido.incluir_pre_ranking:
                pre = rec.pre_ranking(topicos, top_k=pedido.top_k, ano_min=pedido.ano_min,
                                      ano_max=pedido.ano_max, n_itens=pedido.n_itens)
                tempos_pre = dict(rec.tempos)
            ranking = rec.recomendar(topicos, top_k=pedido.top_k, ano_min=pedido.ano_min, ano_max=pedido.ano_max)
            tempos = dict(rec.tempos)
            cortados = list(rec.professores_cortados)

        resultado = {
            "consulta": topicos,
            "ranking": [
                {
                    "posicao": i,
                    **prof,
                    # nota do texto de perfil do professor e quanto ela pesa no score (não aparece nos destaques)
                    "perfil": resumo_perfil(prof),
                    # melhores itens de cada tipo entre todos os tópicos: o que mostrar ao usuário
                    "destaques": _melhores_itens(prof, pedido.n_itens),
                }
                for i, prof in enumerate(ranking, start=1)
            ],
            "professores_cortados": [{"nome": nome, "score": score} for nome, score in cortados],
            "tempos": tempos,
        }
        if pre is not None:
            resultado["pre_ranking"] = pre
            resultado["tempos_pre_ranking"] = tempos_pre
        return _limpar(resultado)

    return app


def carregar_app() -> FastAPI:
    """Carrega modelos, conecta no Qdrant e cria a API."""
    from recuperacao.sistema_de_busca.busca.reranking import carregar_reranker
    from recuperacao.sistema_de_busca.busca.service import Recomendador
    from recuperacao.sistema_de_busca.database_vetores import conectar_Qdrant
    from recuperacao.sistema_de_busca.modelo import carregar_modelo

    rec = Recomendador(conectar_Qdrant(), carregar_modelo(), carregar_reranker())
    return criar_app(rec)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(carregar_app(), host="0.0.0.0", port=8000)
