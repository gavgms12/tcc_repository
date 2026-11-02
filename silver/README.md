# Camada Silver

A Silver concentra o merge de identidade e a limpeza de cada fonte (SIGAA e
Lattes) coletada pela Bronze. Ela **não** une SIGAA com Lattes — isso é
responsabilidade exclusiva da Gold.

## Organização

- `01_merge/` — merge de identidade SIGAA + IESTI (nome, idLattes, siape) e geração da lista para o scriptLattes
- `02_integracao/` — coleta dos currículos Lattes via scriptLattes
- `03_limpeza/` — limpeza por fonte: perfil SIGAA, perfil Lattes e catálogo de trabalhos de IC/periódicos, cada um em Parquet separado

## Fluxo esperado

1. Lê da Bronze somente a pasta de data mais recente (`raw/AAAAMMDD/`); se uma fonte não estiver nela, a execução falha. `BRONZE_DATA` fixa outra data
2. Faz o merge SIGAA + IESTI
3. Executa o scriptLattes para os ids Lattes do roster (com cache local) e grava os JSONs na Bronze, na mesma pasta de data lida
4. Limpa os perfis SIGAA e Lattes em Parquets separados e gera os catálogos

A unificação dos dois perfis fica na Gold.

## Limpeza dos resumos

`integracao/resumo.py` reduz o resumo do Lattes e a descrição pessoal do SIGAA ao que descreve a atuação do docente, sem corte por tamanho. Saem traduções marcadas, frases repetidas e frases só de titulação ou de cargo. Uma frase que cite área, ênfase, temas ou pesquisa é mantida inteira.

| Parquet | Campo | Conteúdo |
|---------|-------|----------|
| `perfis_lattes_limpos` | `resumo`, `resumoCompleto`, `formacaoResumo` | texto limpo, original e frases de titulação retiradas |
| `perfis_sigaa_limpos` | `descricaoPessoal`, `descricaoPessoalCompleta`, `formacaoDescricao` | texto limpo, original e frases de titulação retiradas |
