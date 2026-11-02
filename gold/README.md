# Camada Gold

A Gold contém exclusivamente os perfis unificados por professor. Ela só lê
Parquets já limpos da Silver — nunca lê nem limpa dados da Bronze.

## Organização

- `unificar_perfis.py` — funde `perfis_sigaa_limpos.parquet` + `perfis_lattes_limpos.parquet` num único perfil por professor, resolvendo IDs de disciplinas e trabalhos de IC para o texto real dos catálogos.
- `pipeline_gold.py` — orquestra a etapa acima.

## Saída

Cada execução grava tudo sob `runs/{AAAAMMDDTHHMMSSZ}/` no bucket `gold` e só
depois atualiza `current.json`, que aponta para a execução válida. Uma falha no
meio da publicação não altera o que os consumidores veem. Fica só a última execução
de cada dia, no fuso da coleta, nos 3 dias mais recentes.

- `current.json` — ponteiro: `run`, `perfis`, `total_perfis` e a chave de cada catálogo.
- `runs/{run}/perfil_professores/{siape}.json` — um JSON por professor, que **referencia por ID** os itens abaixo. A chave é o siape (existe para todos os docentes e não muda).
- `runs/{run}/producoes.json` — catálogo de produções (`id`, `ano`, `tipo`, `titulo`).
- `runs/{run}/projetos.json` — catálogo de projetos (`id`, `nome`, `tipo`, `descricao`, `ano_conclusao`).
- `runs/{run}/orientacoes.json` — catálogo de orientações (`id`, `tipo`, `titulo`, `ano_inicio`, ...), sem as iniciações científicas.
- `runs/{run}/disciplinas.json` — catálogo das disciplinas referenciadas (`idSigaa`, `codigo`, `nome`, `cargaHoraria`, `ementa`). A `ementa` é `null` quando a fonte não a traz, como nos componentes externos ao IESTI.
- `runs/{run}/trabalhos_ic.json` — catálogo dos trabalhos de IC referenciados (`id`, título, autores, resumo, palavras-chave, ano). Reúne os trabalhos coletados nos periódicos e as iniciações do Lattes; quando o título não tem trabalho coletado correspondente, `autores` e `resumo` ficam nulos e `palavrasChaves` vazio.

Antes de publicar, a Gold confere se todo ID citado nos perfis existe no catálogo
correspondente; acima de 2% de referências sem catálogo a execução falha e nada é publicado.

Campos do perfil:

| Campo | Fonte | Observação |
|-------|-------|------------|
| `nome`, `idLattes`, `siape` | identidade | metadados, não são texto para embedding |
| `resumo` | Lattes + SIGAA | só frases sobre a atuação, limpas na Silver, sem repetir frases das duas fontes |
| `formacaoAcademicaProfissional` | SIGAA | sem esse dado, usa as frases de titulação retiradas do resumo |
| `areasEspecializacao` | Lattes (`competencias.areas`) | só as subáreas (lista de strings); `grande_area`/`area` eram repetidas |
| `topicosInteresse` | SIGAA (`areasInteresse`) + Lattes (`linhas_pesquisa`, `palavras_chave`) | unificado e deduplicado (case-insensitive) |
| `producoes` | Lattes | lista de IDs → `producoes.json` |
| `projetos` | Lattes | lista de IDs → `projetos.json` |
| `orientacoes` | Lattes | lista de IDs → `orientacoes.json` |
| `disciplinas` | SIGAA (`disciplinasSigaa`) | lista de `idSigaa` → `disciplinas.json` |
| `trabalhosIniciacaoCientifica` | SIGAA e Lattes | lista de IDs → `trabalhos_ic.json` |

`unificar_perfis.py` valida, ao final, se cada perfil tem conteúdo textual suficiente para um embedding útil (sem resumo nem tópicos, texto duplicado entre campos, ou algum ID que vazou como texto) e imprime um aviso por professor problemático — não descarta nada silenciosamente.

> Gold não decide qual modelo de embedding usar nem como fazer chunking — isso é a próxima etapa (fora do escopo deste módulo).
