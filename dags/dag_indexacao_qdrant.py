"""DAG de indexação: leva a execução válida da Gold (MinIO) para o Qdrant.

Agendada pelo asset GOLD_PRONTA, publicado pela DAG da Gold: assim que uma
nova Gold é publicada, os perfis e catálogos viram vetores (BGE-M3 denso +
esparso) nas coleções do Qdrant usadas pela busca.

A indexação é incremental: só objetos novos ou com texto alterado (hash) são
reprocessados, então execuções seguintes à primeira levam poucos minutos.
Os itens que saíram da Gold são apagados do Qdrant, com a trava do próprio
script (não apaga se passar de 30% de uma coleção).
"""

from datetime import datetime, timedelta

from airflow.sdk import DAG, task

from assets import GOLD_PRONTA

MODULO_INDEXACAO = "recuperacao.sistema_de_busca.indexacao.execucao"

with DAG(
    dag_id="indexacao_qdrant",
    start_date=datetime(2026, 1, 1),
    schedule=[GOLD_PRONTA],
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
    },
    tags=["tcc", "qdrant"],
) as dag:

    @task
    def verificar_pre_requisitos():
        """Falha cedo, com mensagem clara, se faltar código, dependência ou acesso ao Qdrant."""
        import importlib.util
        import os

        if importlib.util.find_spec("recuperacao") is None or importlib.util.find_spec(
            MODULO_INDEXACAO
        ) is None:
            raise RuntimeError(
                "Código da busca não encontrado: a pasta recuperacao/ precisa estar na "
                "raiz do repositório (montada em /opt/project/recuperacao)."
            )
        for modulo in ("torch", "FlagEmbedding", "qdrant_client"):
            if importlib.util.find_spec(modulo) is None:
                raise RuntimeError(
                    f"Dependência '{modulo}' ausente na imagem: confira o requirements-busca.txt "
                    "na raiz e rode `docker compose up -d --build`."
                )
        if not os.getenv("QDRANT_URL") or not os.getenv("QDRANT_API_KEY"):
            raise RuntimeError("QDRANT_URL e QDRANT_API_KEY precisam estar preenchidos no .env.")

        from qdrant_client import QdrantClient

        cliente = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ["QDRANT_API_KEY"])
        colecoes = [c.name for c in cliente.get_collections().collections]
        print(f"Qdrant acessível: {len(colecoes)} coleção(ões): {colecoes}")

    @task(execution_timeout=timedelta(hours=3))
    def indexar_gold_no_qdrant():
        """Roda a indexação da recuperacao/ sobre a run apontada pelo current.json.

        Em processo separado: o script lê argumentos com argparse (no processo
        do Airflow ele leria os argumentos do próprio Airflow) e a memória do
        modelo de embeddings é devolvida ao terminar.
        """
        import subprocess
        import sys

        subprocess.run(
            [sys.executable, "-u", "-m", MODULO_INDEXACAO, "--exclusao", "sim"],
            cwd="/opt/project",
            check=True,
        )

    verificar_pre_requisitos() >> indexar_gold_no_qdrant()
