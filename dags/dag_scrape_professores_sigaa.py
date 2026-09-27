from datetime import datetime
import sys

PROJECT_ROOT = "/opt/project"
sys.path.append(PROJECT_ROOT)
# "01_merge" e "02_integracao" começam com dígito e não são pacotes Python
# válidos para import por ponto; os módulos são importados adicionando seus
# diretórios ao sys.path (mesmo padrão já usado em unificar_perfis.py).
sys.path.append(f"{PROJECT_ROOT}/silver/01_merge")
sys.path.append(f"{PROJECT_ROOT}/silver/02_integracao")

from airflow import DAG
from airflow.operators.python import PythonOperator

from bronze.scraping.scrape_professores_sigaa import executar_scraping as scrape_sigaa
from bronze.scraping.scrape_sigaa_docente import executar_coleta as scrape_perfil_docente
from bronze.scraping.scrape_sigaa_componentes import executar_coleta as scrape_componentes
from bronze.scraping.scrape_professores_iesti import executar_coleta as scrape_iesti
from bronze.scraping.scrape_trabalhos_ic import executar_coleta as scrape_trabalhos_ic
from merge_professores import executar_merge as merge_perfis
from executar_scriptlattes import executar_lattes as scrape_lattes


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
    )

    t4_scrape_iesti = PythonOperator(
        task_id="scrape_iesti",
        python_callable=scrape_iesti,
    )

    t5_merge_perfis = PythonOperator(
        task_id="merge_perfis_sigaa_iesti",
        python_callable=merge_perfis,
    )

    t6_scrape_lattes = PythonOperator(
        task_id="scrape_lattes",
        python_callable=scrape_lattes,
    )

    t7_trabalhos_ic = PythonOperator(
        task_id="scrape_trabalhos_ic",
        python_callable=scrape_trabalhos_ic,
    )

    # Perfil docente detalhado depende apenas da lista de professores do SIGAA.
    t1_scrape_sigaa >> t2_perfil_docente

    # O merge de identidade (Bronze -> Silver) depende do SIGAA e do IESTI.
    [t1_scrape_sigaa, t4_scrape_iesti] >> t5_merge_perfis >> t6_scrape_lattes

    # Componentes curriculares e trabalhos de IC não dependem de nenhuma outra
    # etapa nem alimentam o merge; ficam soltos para rodar em paralelo.
