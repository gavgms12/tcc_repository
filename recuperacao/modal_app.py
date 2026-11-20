"""Deploy da API de busca (com o front em /app) no Modal, com GPU e link público fixo.

Pré-requisitos (uma vez só):
    pip install modal
    modal setup                                   # login no navegador
    modal secret create qdrant QDRANT_URL=https://... QDRANT_API_KEY=...

Testar (link temporário, recarrega ao salvar; Ctrl+C encerra):
    modal serve recuperacao/modal_app.py

Publicar (link fixo, fica no ar até `modal app stop busca-orientadores`):
    modal deploy recuperacao/modal_app.py

Rodar os comandos a partir da raiz do repositório.
"""
from pathlib import Path

import modal

RAIZ = Path(__file__).resolve().parents[1]          # raiz do repositório
MODELOS = ("BAAI/bge-m3", "BAAI/bge-reranker-v2-m3")  # iguais a config.EMBEDDING_MODEL / RERANKER_MODEL


def baixar_modelos():
    """Roda durante o build: os modelos ficam dentro da imagem (sem download a cada cold start)."""
    from huggingface_hub import snapshot_download

    for nome in MODELOS:
        snapshot_download(nome)


image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements(str(RAIZ / "requirements-busca.txt"))
    .pip_install("torch", "fastapi[standard]", "pandas>=2.2,<3", "python-dotenv>=1.0,<2", "huggingface_hub")
    .env({
        "HF_HOME": "/modelos",
        # cache de scores do reranker: em disco local do container (some quando ele desliga)
        "RERANK_CACHE_PATH": "/tmp/rerank_scores.sqlite",
    })
    .run_function(baixar_modelos)
    # código por último: mudar o código não refaz o build dos modelos
    .add_local_dir(RAIZ / "recuperacao" / "sistema_de_busca", "/root/recuperacao/sistema_de_busca",
                   ignore=["__pycache__", "cache"])
    .add_local_dir(RAIZ / "recuperacao" / "frontend", "/root/recuperacao/frontend")
)

app = modal.App("busca-orientadores", image=image)

# Disco persistente com as buscas feitas (um JSON por busca, em pastas por dia). Baixar para o PC:
#   modal volume get buscas-log / recuperacao/output/buscas_log
logs = modal.Volume.from_name("buscas-log", create_if_missing=True)


@app.function(
    gpu="T4",
    secrets=[modal.Secret.from_name("qdrant")],
    volumes={"/logs": logs},
    env={"LOG_BUSCAS_DIR": "/logs"},
    scaledown_window=300,   # desliga após 5 min sem uso (não cobra parado). Próxima busca: cold start ~30-60s
    timeout=600,
    # min_containers=1,     # deixa sempre ligado (sem cold start), mas cobra o tempo todo
)
@modal.concurrent(max_inputs=20)   # front e /topicos não esperam; /recomendar já é serializado pela trava da API
@modal.asgi_app()
def web():
    from recuperacao.sistema_de_busca.api import carregar_app

    return carregar_app()
