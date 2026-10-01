"""DAG da camada Silver: merge de identidade, scriptLattes e limpeza dos perfis.

Roda separada da Bronze (dag_scrape_professores_sigaa.py) — depende apenas de
que os JSONs brutos já existam no bucket `bronze` do MinIO (rode a DAG Bronze
antes, ao menos uma vez). Não há checagem automática de dependência entre as
DAGs: dispare esta manualmente depois que a coleta terminar.
"""

from datetime import datetime
import sys

PROJECT_ROOT = "/opt/project"
sys.path.append(PROJECT_ROOT)
# "01_merge" e "02_integracao" começam com dígito e não são pacotes Python
# válidos para import por ponto; os módulos são importados adicionando seus
# diretórios ao sys.path (mesmo padrão já usado em limpar_perfis.py).
sys.path.append(f"{PROJECT_ROOT}/silver/01_merge")
sys.path.append(f"{PROJECT_ROOT}/silver/02_integracao")

from airflow import DAG
from airflow.operators.python import PythonOperator

from merge_professores import executar_merge as merge_perfis
from executar_scriptlattes import executar_lattes as scrape_lattes
from limpar_perfis import executar_limpeza as limpar_perfis


with DAG(
    dag_id="silver_professores_sigaa",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["tcc", "silver"],
) as dag:

    t1_merge_perfis = PythonOperator(
        task_id="merge_perfis_sigaa_iesti",
        python_callable=merge_perfis,
    )

    t2_scrape_lattes = PythonOperator(
        task_id="scrape_lattes",
        python_callable=scrape_lattes,
    )

    t3_limpar_perfis = PythonOperator(
        task_id="limpar_perfis_sigaa_lattes",
        python_callable=limpar_perfis,
    )

    # merge_perfis gera o roster de identidade (professores_unificados.parquet)
    # que scrape_lattes lê para saber quais currículos baixar; limpar_perfis só
    # roda depois, pois lê tanto o roster quanto os currículos já coletados.
    t1_merge_perfis >> t2_scrape_lattes >> t3_limpar_perfis
