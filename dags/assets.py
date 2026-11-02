"""Assets que encadeiam as camadas: Bronze -> Silver -> Gold.

Cada DAG publica o asset da sua camada ao terminar e a DAG seguinte é
agendada por ele, sem disparo manual entre camadas.
"""

from airflow.sdk import Asset

BRONZE_PRONTA = Asset("s3://bronze/raw/")
SILVER_PRONTA = Asset("s3://silver/perfis_lattes_limpos.parquet")
