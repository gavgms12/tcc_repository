# Camada Silver

A Silver concentra o merge de identidade e a limpeza de cada fonte (SIGAA e
Lattes) coletada pela Bronze. Ela **não** une SIGAA com Lattes — isso é
responsabilidade exclusiva da Gold.

## Organização

- `01_merge/` — merge de identidade SIGAA + IESTI (nome, idLattes, siape) e geração da lista para o scriptLattes
- `02_integracao/` — coleta dos currículos Lattes via scriptLattes
- `03_limpeza/` — limpeza por fonte: perfil SIGAA, perfil Lattes e catálogo de trabalhos de IC/periódicos, cada um em Parquet separado

## Fluxo esperado

1. Ler os arquivos crus da Bronze
2. Fazer merge de identidade SIGAA + IESTI
3. Gerar a lista de ids Lattes e baixar os currículos via scriptLattes
4. Limpar o perfil SIGAA (remover contato/extensão, podar disciplinas/projetos/produção docente)
5. Limpar o perfil Lattes (resumo, competências, produções/projetos/orientações)
6. Limpar o catálogo de trabalhos de IC/periódicos (sem vincular a professor)

> A unificação dos perfis SIGAA + Lattes por professor acontece só na Gold.
