# Camada Gold

A Gold consome os Parquets já limpos da Silver e produz o perfil final por professor, pronto para gerar embeddings (BGE-M3) e indexar no Qdrant.

## Organização

- `unificar_perfis.py` — funde `perfis_sigaa_limpos.parquet` + `perfis_lattes_limpos.parquet` num único perfil por professor, resolvendo IDs de disciplinas e trabalhos de IC para o texto real dos catálogos.
- `pipeline_gold.py` — orquestra a etapa acima.

## Saída

Cada execução grava tudo sob `runs/{AAAAMMDDTHHMMSSZ}/` no bucket `gold` e só
depois atualiza `current.json`, que aponta para a execução válida. Uma falha no
meio da publicação não altera o que os consumidores veem. As 3 execuções mais
recentes são mantidas.

- `current.json` — ponteiro: `run`, `perfis`, `total_perfis` e a chave de cada catálogo.
- `runs/{run}/perfil_professores/{siape}.json` — um JSON por professor, que **referencia por ID** os itens abaixo. A chave é o siape (existe para todos os docentes e não muda).
- `runs/{run}/producoes.json` — catálogo de produções (`id`, `ano`, `tipo`, `titulo`).
- `runs/{run}/projetos.json` — catálogo de projetos (`id`, `nome`, `tipo`, `descricao`, `ano_conclusao`).
- `runs/{run}/orientacoes.json` — catálogo de orientações (`id`, `tipo`, `titulo`, `ano_inicio`, ...).
- `runs/{run}/trabalhos_ic.json` — catálogo dos trabalhos de IC/periódicos referenciados (`id`, título, autores, resumo, palavras-chave).

As disciplinas são referenciadas pelo `idSigaa` e resolvidas contra `silver/componentes_curriculares[_externos].parquet`.

Antes de publicar, a Gold confere se todo ID citado nos perfis existe no catálogo
correspondente; acima de 2% de referências sem catálogo a execução falha e nada é publicado.

Campos do perfil:

| Campo | Fonte | Observação |
|-------|-------|------------|
| `nome`, `idLattes`, `siape` | identidade | metadados, não são texto para embedding |
| `resumo` | Lattes + SIGAA | uma só string, sem repetir texto idêntico das duas fontes |
| `formacaoAcademicaProfissional` | SIGAA | |
| `areasEspecializacao` | Lattes (`competencias.areas`) | só as subáreas (lista de strings); `grande_area`/`area` eram repetidas |
| `topicosInteresse` | SIGAA (`areasInteresse`) + Lattes (`linhas_pesquisa`, `palavras_chave`) | unificado e deduplicado (case-insensitive) |
| `producoes` | Lattes | lista de IDs → `producoes.json` |
| `projetos` | Lattes | lista de IDs → `projetos.json` |
| `orientacoes` | Lattes | lista de IDs → `orientacoes.json` |
| `disciplinas` | SIGAA (`disciplinasSigaa`) | lista de `idSigaa` |
| `trabalhosIniciacaoCientifica` | SIGAA | lista de IDs → `trabalhos_ic.json` |

`unificar_perfis.py` valida, ao final, se cada perfil tem conteúdo textual suficiente para um embedding útil (sem resumo nem tópicos, texto duplicado entre campos, ou algum ID que vazou como texto) e imprime um aviso por professor problemático — não descarta nada silenciosamente.

> Gold não decide qual modelo de embedding usar nem como fazer chunking — isso é a próxima etapa (fora do escopo deste módulo).
