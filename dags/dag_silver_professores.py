"""DAG da camada Silver: merge de identidade, scriptLattes e limpeza dos perfis.

Agendada pelo asset BRONZE_PRONTA (publicado pela DAG da Bronze) e, ao
terminar, publica SILVER_PRONTA, que aciona a Gold.
"""

from datetime import datetime, timedelta
import sys

PROJECT_ROOT = "/opt/project"
sys.path.append(PROJECT_ROOT)
sys.path.append(f"{PROJECT_ROOT}/dags")

from airflow.sdk import DAG, task

from assets import BRONZE_PRONTA, SILVER_PRONTA

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "retry_exponential_backoff": True,
}

with DAG(
    dag_id="silver_professores_sigaa",
    start_date=datetime(2026, 1, 1),
    schedule=[BRONZE_PRONTA],
    catchup=False,
    default_args=default_args,
    tags=["tcc", "silver"],
) as dag:

    @task
    def merge_perfis_sigaa_iesti():
        from silver.merge.merge_professores import executar_merge

        executar_merge()

    @task
    def scrape_lattes():
        # O retry reaproveita o cache do scriptLattes: só os currículos que
        # faltaram (rate limit do CNPq) são baixados de novo.
        from silver.integracao.executar_scriptlattes import executar_lattes

        executar_lattes()

    @task(outlets=[SILVER_PRONTA])
    def limpar_perfis_sigaa_lattes():
        from silver.integracao.limpar_perfis import executar_limpeza

        executar_limpeza()

    # O merge gera o roster que o scriptLattes lê; a limpeza lê o roster e os
    # currículos já coletados.
    merge_perfis_sigaa_iesti() >> scrape_lattes() >> limpar_perfis_sigaa_lattes()
