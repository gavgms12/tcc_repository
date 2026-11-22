"""Assets que encadeiam as etapas: Bronze -> Silver -> Gold -> Qdrant.

Cada DAG publica o asset da sua etapa ao terminar e a DAG seguinte é
agendada por ele, sem disparo manual entre etapas.
"""

from airflow.sdk import Asset

BRONZE_PRONTA = Asset("s3://bronze/raw/")
SILVER_PRONTA = Asset("s3://silver/perfis_lattes_limpos.parquet")
# A Gold só atualiza o current.json depois de validar a execução inteira.
GOLD_PRONTA = Asset("s3://gold/current.json")
