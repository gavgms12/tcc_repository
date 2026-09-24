# Camada Gold

A Gold contém exclusivamente os perfis unificados por professor. Ela só lê
Parquets já limpos da Silver — nunca lê nem limpa dados da Bronze.

## Organização

- `01_unificacao/` — junta identidade + perfil SIGAA limpo + perfil Lattes limpo + catálogo de trabalhos de IC/periódicos num perfil único por professor

## Fluxo esperado

1. Ler `identidade_professores.parquet`, `perfil_sigaa_limpo.parquet`, `perfil_lattes_limpo.parquet` e `trabalhos_ic_periodicos.parquet` da Silver
2. Vincular cada trabalho de IC ao professor orientador por similaridade de nome
3. Unir o perfil SIGAA com o perfil Lattes de cada professor (por siape/idLattes)
4. Gravar `professores_unificados.parquet` na Gold

Esse Parquet é a única saída da Gold e a base para as próximas etapas
(embeddings bge-m3, busca por especialistas).
