"""DAG da camada Bronze: só coleta bruta (web scraping), sem processamento.

O merge de identidade, o scriptLattes e a limpeza dos perfis são etapas da
Silver e ficam em dag_silver_professores.py, para poder rodar cada camada
separadamente.
"""

from datetime import datetime
import sys

PROJECT_ROOT = "/opt/project"
sys.path.append(PROJECT_ROOT)

from airflow import DAG
from airflow.operators.python import PythonOperator

from bronze.scraping.scrape_professores_sigaa import executar_scraping as scrape_sigaa
from bronze.scraping.scrape_sigaa_docente import executar_coleta as scrape_perfil_docente
from bronze.scraping.scrape_sigaa_componentes import executar_coleta as scrape_componentes
from bronze.scraping.scrape_professores_iesti import executar_coleta as scrape_iesti
from bronze.scraping.scrape_trabalhos_ic import executar_coleta as scrape_trabalhos_ic


with DAG(
    dag_id="scrape_professores_sigaa",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["tcc", "bronze"],
) as dag:

    t1_scrape_sigaa = PythonOperator(
        task_id="scrape_sigaa",
        python_callable=scrape_sigaa,
    )

    t2_perfil_docente = PythonOperator(
        task_id="scrape_perfil_docente_sigaa",
        python_callable=scrape_perfil_docente,
    )

    t3_componentes_sigaa = PythonOperator(
        task_id="scrape_componentes_sigaa",
        python_callable=scrape_componentes,
        # Sem isso, executar_coleta usa com_ementa=False por padrão e nenhum
        # componente sai com ementa preenchida — a Silver depende dela para
        # os textos irem pro embedding (bge-m3) na Gold.
        op_kwargs={"com_ementa": True},
    )

    t4_scrape_iesti = PythonOperator(
        task_id="scrape_iesti",
        python_callable=scrape_iesti,
    )

    t7_trabalhos_ic = PythonOperator(
        task_id="scrape_trabalhos_ic",
        python_callable=scrape_trabalhos_ic,
    )

    # Perfil docente detalhado depende apenas da lista de professores do SIGAA.
    t1_scrape_sigaa >> t2_perfil_docente

    # Componentes curriculares, IESTI e trabalhos de IC não dependem de
    # nenhuma outra etapa; ficam soltos para rodar em paralelo.
