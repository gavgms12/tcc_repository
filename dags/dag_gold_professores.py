"""DAG da camada Gold: unifica os perfis SIGAA + Lattes já limpos pela Silver.

Agendada pelo asset SILVER_PRONTA (publicado pela DAG da Silver).
"""

from datetime import datetime, timedelta
import sys

PROJECT_ROOT = "/opt/project"
sys.path.append(PROJECT_ROOT)
sys.path.append(f"{PROJECT_ROOT}/dags")

from airflow.sdk import DAG, task

from assets import SILVER_PRONTA

with DAG(
    dag_id="gold_professores_sigaa",
    start_date=datetime(2026, 1, 1),
    schedule=[SILVER_PRONTA],
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["tcc", "gold"],
) as dag:

    @task
    def unificar_perfis_sigaa_lattes():
        from gold.unificar_perfis import executar_unificacao

        executar_unificacao()

    unificar_perfis_sigaa_lattes()
