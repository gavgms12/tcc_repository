# Recuperação

A Recuperação indexa os dados da Gold no Qdrant e recomenda professores
orientadores a partir dos tópicos escolhidos pelo aluno. A busca combina
embeddings densos e esparsos do BGE-M3 e reordena os resultados com o
reranker `bge-reranker-v2-m3`.

## Organização

- `sistema_de_busca/config.py` — modelos, coleções, catálogo de tópicos, limites de busca, pesos de cada fonte, cortes e bônus
- `sistema_de_busca/textos.py` — monta o texto de cada objeto que vai para o modelo (em minúsculas)
- `sistema_de_busca/modelo.py` — carrega o BGE-M3 e gera os embeddings densos e esparsos
- `sistema_de_busca/database_vetores.py` — conexão com o Qdrant, criação de coleções, upsert e busca híbrida
- `sistema_de_busca/indexacao/` — leitura da Gold, relação professor ↔ objeto e indexação
- `sistema_de_busca/busca/` — pré-ranking (`agregacao.py`), reranking (`reranking.py`), disciplinas do tema (`disciplinas_tema.py`), cache de notas do reranker (`cache_rerank.py`), orquestração (`service.py`) e exibição/diagnóstico
- `sistema_de_busca/api.py` — API HTTP (FastAPI) que também serve o frontend
- `frontend/` — questionário web (HTML, CSS e JS puros), em duas telas: questionário e resultados
- `sistema_de_busca/teste.py` — exemplo de consulta com saída de diagnóstico
- `sistema_de_busca/comparar_modos.py` — compara o ranking com `RERANK_CONSULTA = "nome"` e `"partes"`
- `colab_api_busca.ipynb` — sobe a API no Google Colab (GPU) com link público
- `sistema_de_busca/avaliacao/` e `colab_avaliacao.ipynb` — avaliação offline (densa x esparsa x híbrida, sem e com reranking)
- `test/` — notebooks de experimentos com o BGE-M3

## Coleções

| Coleção | Conteúdo | Filtro por ano |
|---------|----------|----------------|
| `perfil_professores` | resumo, áreas de especialização e tópicos de interesse | não |
| `producao` | títulos de livros, artigos, capítulos e trabalhos em congresso | sim |
| `projetos` | título e descrição de projetos de pesquisa, extensão e desenvolvimento | sim |
| `orientacoes` | títulos das orientações | sim |
| `iniciacao_cientifica` | título, resumo e palavras-chave dos trabalhos de IC | sim |
| `disciplina` | nome e ementa das disciplinas | não |

Cada ponto guarda o texto, os metadados e os `professor_ids` relacionados. Um
objeto com vários autores aparece para todos eles.

## Indexação

1. Lê a run mais recente da Gold no MinIO
2. Monta as relações professor ↔ objeto a partir dos perfis
3. Gera o texto de cada objeto e um hash do texto com os metadados
4. Reindexa só os objetos novos ou cujo hash mudou

A indexação nunca apaga pontos. Um objeto removido da Gold continua no Qdrant
até ser apagado manualmente ou a coleção ser recriada.

## Busca

Para cada tópico escolhido:

1. **Busca híbrida** — busca densa e esparsa em cada coleção, unidas por RRF (`limit` resultados). `MODO_BUSCA` permite usar só a densa ou só a esparsa (para comparação)
2. **Pré-ranking** — cada professor recebe a média dos seus `n` melhores itens por coleção (posições vazias contam como 0), multiplicada por `peso_interno`. As coleções são combinadas por `peso_global`, e o perfil vale `PESO_PROFESSOR`

Depois, para todos os tópicos juntos:

3. **União** — média dos scores entre os tópicos (tópico ausente conta como 0). Só seguem professores com pelo menos um item encontrado, e o corte é em `FINAL_PROFESSOR_K`
4. **Reranking** — cada item é comparado com as consultas do tópico que o encontrou (ver `RERANK_CONSULTA`). Um item passa se atingir `MIN_RERANK_RELATIVO` do melhor item (do mesmo tipo, se `CORTE_POR_TIPO`) e `MIN_RERANK_ABSOLUTO`. O perfil e as disciplinas do tema nunca são cortados. Professores sem nenhum item restante saem do ranking
5. **Resultado** — os `top_k` professores, com o score de cada tópico e os itens mais relevantes de cada coleção. `MIN_SCORE_PROFESSOR_RELATIVO` descarta quem ficar abaixo dessa fração do 1º colocado (0 desliga o corte)

Professor sem perfil indexado (sem resumo, áreas nem tópicos de interesse) não tem nome para exibir e fica fora do ranking, tanto no pré-ranking quanto no reranking.

### Consulta do reranker (`RERANK_CONSULTA`)

A busca usa sempre a descrição completa do tópico; só o reranker muda de consulta:

- `"texto"` — descrição completa do tópico
- `"nome"` — só o nome do tópico
- `"partes"` (padrão) — nome + cada subtópico escrito à mão; para texto livre, o texto sem frases de intenção ("quero pesquisar...") e cada ideia separada por vírgula, ponto e vírgula, "e" ou "ou". O item fica com a maior nota entre as consultas

### Disciplinas do tema

Cada tópico de `TOPICOS` pode listar `disciplinas`. Quem leciona uma delas tem evidência direta:
a disciplina entra sempre como candidata e não é cortada, o professor ganha `BONUS_DISCIPLINA_TEMA` por disciplina distinta
(até `BONUS_DISCIPLINA_TEMA_MAX`) e, com `INCLUIR_PROFESSOR_DISCIPLINA_TEMA`, entra no reranking mesmo fora dos melhores da busca.
O casamento é pelo nome, sem acentos, maiúsculas, pontuação ou código no início.

### Cache de notas do reranker

O reranker é a etapa mais lenta, então as notas de cada par (consulta, texto) ficam em memória e em SQLite
(`RERANK_CACHE_PATH`, padrão `sistema_de_busca/cache/rerank_scores.sqlite`, fora do git). A chave inclui o modelo, o tamanho
máximo e os dois textos, então nunca se usa uma nota velha. Para pré-calcular depois de indexar ou de mudar os tópicos:

```powershell
python -m recuperacao.sistema_de_busca.indexacao.prerankear --estimar   # só conta os pares que faltam
python -m recuperacao.sistema_de_busca.indexacao.prerankear             # calcula (retomável)
```

## Como rodar

Variáveis no `.env`: `QDRANT_URL`, `QDRANT_API_KEY` e as credenciais do MinIO.

```powershell
# indexar ou atualizar as coleções
python -m recuperacao.sistema_de_busca.indexacao.execucao

# contar tokens dos textos (verifica cortes do modelo e do reranker)
python -m recuperacao.sistema_de_busca.indexacao.tokenizar

# rodar a consulta de exemplo
python -m recuperacao.sistema_de_busca.teste

# subir a API e o frontend (http://localhost:8000)
python -m recuperacao.sistema_de_busca.api
```

```python
rec = Recomendador(client, modelo, reranker)
topicos = {t: config.texto_topico(t) for t in ["Compiladores", "Grafos"]}
resultado = rec.recomendar(topicos, top_k=8, ano_min=2015, debug=True)
```

Com `debug=True`, a busca mostra o cálculo do pré-ranking e do reranking de
cada professor.

## Avaliação

`sistema_de_busca/avaliacao/` mede o sistema em conjuntos *trabalho orientado → orientador*: o texto do trabalho
vira uma consulta de texto livre e o orientador é a resposta esperada.

- `tcc`: título de cada TCC orientado (373)
- `ic:titulo` e `ic:titulo+palavras`: cada iniciação científica (139), pelo título ou pelo título + palavras-chave.
  O resumo fica de fora: o reranker o quebraria em dezenas de consultas e ele ocuparia o limite de 512 tokens

- `manual`: consultas escritas por você em `sistema_de_busca/avaliacao/consultas_manuais.json`, cada uma com `texto`
  e/ou `temas` (como no questionário) e os professores esperados em `alta` (melhores escolhas, ganho 2) e `media`
  (também serviriam, ganho 1). `--gerar-modelo` cria o arquivo com exemplos e a lista de professores e temas

Para não vazar a resposta, a busca ignora o próprio trabalho e todo item com o mesmo título (a IC, o artigo ou o
projeto do mesmo trabalho). Um artigo publicado a partir da IC com outro título continua na busca, então a métrica
da IC tende a sair um pouco otimista.

Compara seis configurações nas mesmas consultas: busca densa, esparsa e híbrida (`MODO_BUSCA`), cada uma sem
reranking (pré-ranking) e com reranking. Nos modos densa e esparsa, os scores de cada busca são divididos pelo maior
(`NORMALIZAR_SCORES_BUSCA`) para ficarem na mesma escala entre coleções.

| Métrica | O que mede |
|---------|------------|
| nDCG@5 | se o orientador está entre os 5 primeiros, valendo mais quanto mais alto |
| MRR | 1 / posição do orientador no ranking |
| Recall@5 | fração dos orientadores que aparecem nos 5 primeiros |
| Hit@1 | se o 1º colocado é o orientador |

Dentro de cada conjunto, cada configuração é comparada com a híbrida+rerank por teste de Wilcoxon pareado (p < 0,05: diferença provavelmente real).

```powershell
python -m recuperacao.sistema_de_busca.avaliacao.avaliar --n 150                    # 150 TCCs sorteados, 6 configurações
python -m recuperacao.sistema_de_busca.avaliacao.avaliar --conjunto ambos --n 150   # TCC + IC (as duas versões)
python -m recuperacao.sistema_de_busca.avaliacao.avaliar --gerar-modelo             # cria consultas_manuais.json
python -m recuperacao.sistema_de_busca.avaliacao.avaliar --conjunto manual          # suas consultas
python -m recuperacao.sistema_de_busca.avaliacao.avaliar --n 5 --so-pre   # teste rápido, sem reranker
```

Com reranker, rode no Colab com GPU (`colab_avaliacao.ipynb`). A saída vai para `recuperacao/output/avaliacao_<data-hora>/`
(`consultas.csv`, `resumo.csv`, `resumo.json` e o log).

Limitações: o título de um TCC não é igual à pergunta de um aluno; há um único relevante por consulta (os números são um
piso); e o orientador nem sempre é o professor mais especializado no tema.

## API e frontend

`api.py` carrega os modelos e serve, no mesmo endereço (`http://localhost:8000`):

| Rota | Função |
|------|--------|
| `GET /` | redireciona para o frontend em `/app/` |
| `GET /saude` | verificação de que a API está no ar |
| `GET /topicos` | catálogo de tópicos, com categoria, descrição e disciplinas |
| `POST /recomendar` | recebe `topicos` (nomes do catálogo) e/ou `texto`, além de `top_k`, `n_itens`, `ano_min` e `ano_max`; devolve o ranking, os professores cortados e os tempos. A documentação interativa fica em `/docs` |

Uma busca roda por vez (o modelo ocupa a GPU inteira e o `Recomendador` guarda o estado da última chamada).
No Colab, use `colab_api_busca.ipynb` para ter GPU e um link público.

O frontend (`frontend/`) tem duas telas: o questionário (escolha de 1 a 3 temas, texto livre opcional e opções da busca) e os resultados,
com afinidade de cada professor, evidências e comparação lado a lado. O botão "Voltar ao questionário" mantém o que foi preenchido.
Pelo menos um tema é obrigatório.

## Observações

- O reranker roda na CPU se o PyTorch não tiver CUDA, e é a etapa mais lenta. O tempo cresce com o número de tópicos, `FINAL_PROFESSOR_K` e `n`
- Os modelos são carregados uma vez por processo. Para várias consultas, reutilize o mesmo `Recomendador`
- A busca esparsa diferencia maiúsculas de minúsculas, então os textos indexados e os tópicos devem estar no mesmo formato
- `busca/busca_hibrida_old.py` é a versão anterior da busca e não é mais usada
- `comparar_modos.py` e `teste.py` gravam a saída em `recuperacao/output/` (fora do git)
