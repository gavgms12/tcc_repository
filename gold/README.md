# Camada Gold

A Gold consome os Parquets já limpos da Silver e produz o perfil final por professor, pronto para gerar embeddings (BGE-M3) e indexar no Qdrant.

## Organização

- `unificar_perfis.py` — funde `perfis_sigaa_limpos.parquet` + `perfis_lattes_limpos.parquet` num único perfil por professor, resolvendo IDs de disciplinas e trabalhos de IC para o texto real dos catálogos.
- `pipeline_gold.py` — orquestra a etapa acima.

## Saída

Um JSON por professor no bucket `gold`, sob o prefixo `perfil_professores/{idLattes ou siape}.json`. Cada arquivo contém:

| Campo | Fonte | Observação |
|-------|-------|------------|
| `nome`, `idLattes`, `siape` | identidade | metadados, não são texto para embedding |
| `resumo` | Lattes + SIGAA | uma só string, sem repetir texto idêntico das duas fontes |
| `formacaoAcademicaProfissional` | SIGAA | |
| `areasEspecializacao` | Lattes (`competencias.areas`) | lista de dicts (grande_area/area/subarea/especialidade) |
| `topicosInteresse` | SIGAA (`areasInteresse`) + Lattes (`linhas_pesquisa`, `palavras_chave`) | unificado e deduplicado (case-insensitive) |
| `producoes`, `projetos`, `orientacoes` | Lattes | já deduplicados na Silver |
| `disciplinas` | SIGAA (`disciplinasSigaa`, IDs) resolvido contra `componentes_curriculares[_externos].parquet` | nome + ementa (quando existir), nunca o ID cru |
| `trabalhosIniciacaoCientifica` | SIGAA (IDs) resolvido contra `trabalhos_ic_periodicos.parquet` | título + resumo + palavras-chave, nunca o ID cru |

`unificar_perfis.py` valida, ao final, se cada perfil tem conteúdo textual suficiente para um embedding útil (sem resumo nem tópicos, texto duplicado entre campos, ou algum ID que vazou como texto) e imprime um aviso por professor problemático — não descarta nada silenciosamente.

> Gold não decide qual modelo de embedding usar nem como fazer chunking — isso é a próxima etapa (fora do escopo deste módulo).
