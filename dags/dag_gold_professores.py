"""DAG da camada Gold: unifica os perfis SIGAA + Lattes já limpos pela Silver.

Roda separada da Silver (dag_silver_professores.py) — depende apenas de que
`perfis_sigaa_limpos.parquet`, `perfis_lattes_limpos.parquet` e os catálogos
de componentes/trabalhos de IC já existam no bucket `silver` do MinIO (rode a
DAG Silver antes, ao menos uma vez). Não há checagem automática de
dependência entre as DAGs: dispare esta manualmente depois que a Silver
terminar.
"""

from datetime import datetime
import sys

PROJECT_ROOT = "/opt/project"
sys.path.append(PROJECT_ROOT)
sys.path.append(f"{PROJECT_ROOT}/gold")

from airflow import DAG
from airflow.operators.python import PythonOperator

from unificar_perfis import executar_unificacao as unificar_perfis_gold


with DAG(
    dag_id="gold_professores_sigaa",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["tcc", "gold"],
) as dag:

    t1_unificar_perfis = PythonOperator(
        task_id="unificar_perfis_sigaa_lattes",
        python_callable=unificar_perfis_gold,
    )
