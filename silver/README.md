# Camada Silver

A Silver concentra a lógica de integração, merge e limpeza dos dados coletados pela Bronze.

## Organização

- `merge/` — merge dos dados do SIGAA + IESTI em um roster de identidade (`professores_unificados.parquet`)
- `integracao/` — scriptLattes (currículos para a Bronze) e limpeza dos perfis SIGAA e Lattes, com catálogos de disciplinas e trabalhos de IC
- `pipeline_silver.py` — chama as três etapas em sequência

## Fluxo

1. Lê da Bronze somente a pasta de data mais recente (`raw/AAAAMMDD/`); se uma fonte não estiver nela, a execução falha. `BRONZE_DATA` fixa outra data
2. Faz o merge SIGAA + IESTI
3. Executa o scriptLattes para os ids Lattes do roster (com cache local) e grava os JSONs na Bronze, na mesma pasta de data lida
4. Limpa os perfis SIGAA e Lattes em Parquets separados e gera os catálogos

A unificação dos dois perfis fica na Gold.
