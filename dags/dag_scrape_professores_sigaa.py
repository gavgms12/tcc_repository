from datetime import datetime
import sys

sys.path.append("/opt/project")

from airflow import DAG
from airflow.operators.python import PythonOperator

from bronze.scraping.scrape_professores_sigaa import executar_scraping


with DAG(
    dag_id="scrape_professores_sigaa",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["tcc", "bronze"],
) as dag:

    scrape_professores = PythonOperator(
        task_id="scrape_professores",
        python_callable=executar_scraping,
    )
