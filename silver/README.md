# Camada Silver

A Silver concentra a lógica de integração, merge e limpeza dos dados coletados pela Bronze.

## Organização

- `01_merge/` — merge dos dados do SIGAA + IESTI e geração da lista para o scriptLattes
- `02_integracao/` — enriquecimento com Lattes, unificação de perfis, vinculação de disciplinas e trabalhos IC
- `base/` — cadastros base e unificados
- `lista/` — listas finais para consumo
- `docentes/` — perfis limpos por docente

## Fluxo esperado

1. Ler os arquivos crus da Bronze
2. Fazer merge SIGAA + IESTI
3. Gerar a lista de ids Lattes
4. Receber o retorno do scraping de Lattes da Bronze
5. Unir perfil SIGAA + perfil Lattes
6. Limpar dados, remover duplicados e manter só campos essenciais

> Gold permanece fora do escopo por enquanto.
