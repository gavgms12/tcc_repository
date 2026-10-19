"""DAG da camada Bronze: só coleta bruta (web scraping), sem processamento.

O merge de identidade, o scriptLattes e a limpeza dos perfis são etapas da
Silver (dag_silver_professores.py), disparada automaticamente quando esta DAG
termina (asset BRONZE_PRONTA). Os imports pesados ficam dentro das tasks para
manter o parse da DAG rápido.
"""

from datetime import datetime, timedelta
import sys

PROJECT_ROOT = "/opt/project"
sys.path.append(PROJECT_ROOT)
sys.path.append(f"{PROJECT_ROOT}/dags")

from airflow.sdk import DAG, task

from assets import BRONZE_PRONTA

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}

with DAG(
    dag_id="bronze_scrape_professores_sigaa",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    default_args=default_args,
    tags=["tcc", "bronze"],
) as dag:

    @task
    def scrape_sigaa():
        from bronze.scraping.scrape_professores_sigaa import executar_scraping

        executar_scraping()

    @task
    def scrape_perfil_docente_sigaa():
        from bronze.scraping.scrape_sigaa_docente import executar_coleta

        executar_coleta()

    @task
    def scrape_componentes_sigaa():
        from bronze.scraping.scrape_sigaa_componentes import executar_coleta

        # A Silver depende das ementas para os textos irem pro embedding. Só
        # são buscadas as que ainda não constam na coleta anterior.
        executar_coleta(com_ementa=True)

    @task
    def scrape_iesti():
        from bronze.scraping.scrape_professores_iesti import executar_coleta

        executar_coleta()

    @task
    def scrape_trabalhos_ic():
        from bronze.scraping.scrape_trabalhos_ic import executar_coleta

        executar_coleta()

    @task(outlets=[BRONZE_PRONTA])
    def bronze_concluida():
        """Marca a Bronze como pronta; aciona a DAG da Silver."""

    # O perfil detalhado depende da lista de professores do SIGAA; os demais
    # coletores são independentes e rodam em paralelo.
    coletas = [
        scrape_sigaa() >> scrape_perfil_docente_sigaa(),
        scrape_componentes_sigaa(),
        scrape_iesti(),
        scrape_trabalhos_ic(),
    ]
    coletas >> bronze_concluida()
