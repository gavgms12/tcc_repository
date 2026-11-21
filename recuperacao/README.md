# Sistema de busca — recomendação de orientadores

Consome a camada **Gold** do pipeline (perfis dos docentes do IESTI) e recomenda orientadores para um aluno a partir de um **texto livre** (ex.: o tema que quer pesquisar) e/ou de **tópicos** de um catálogo. A recuperação é **híbrida** (densa + esparsa, unidas por RRF) e o resultado é refinado por um **reranker** (*cross-encoder*).

---

## Visão geral

```
 Gold (MinIO, runs/<execução>/)
        │  indexacao/execucao.py
        ▼
 ┌────────────────────────────┐   BGE-M3 gera, numa só passada,
 │ Qdrant (uma coleção por    │   o vetor denso (1024, cosseno) e o
 │ tipo de item)              │   esparso (pesos lexicais, produto escalar)
 └─────────────┬──────────────┘
               │  consulta (texto livre e/ou tópicos)
               ▼
   busca densa ─┐
                ├─ RRF (Qdrant) ──► pré-ranking de itens ──► agregação por professor
   busca esparsa┘                                                   │
                                                                    ▼
                                    reranking (bge-reranker-v2-m3) dos itens dos melhores professores
                                                                    │
                                                                    ▼
                                                   ranking final de professores (API / front)
```

### Modelos e armazenamento

| Componente | Escolha | Onde |
|---|---|---|
| Embedding | `BAAI/bge-m3` (denso 1024 + esparso aprendido, fp16) | [modelo.py](sistema_de_busca/modelo.py) |
| Reranker | `BAAI/bge-reranker-v2-m3` (*cross-encoder*, `max_length` 512, score normalizado em [0, 1]) | [busca/reranking.py](sistema_de_busca/busca/reranking.py) |
| Banco vetorial | Qdrant (Cloud), vetores `dense` e `sparse` no mesmo ponto | [database_vetores.py](sistema_de_busca/database_vetores.py) |
| Fusão | `Prefetch` denso + `Prefetch` esparso → `FusionQuery(Fusion.RRF)` | [database_vetores.py](sistema_de_busca/database_vetores.py) |

O índice HNSW usa os padrões do Qdrant: abaixo do limite de indexação a busca densa é exata (varredura completa). Os vetores esparsos usam índice invertido (busca exata).

### Coleções

| Coleção (`config.py`) | Conteúdo |
|---|---|
| `perfil_professores` | Perfil resumido de cada docente |
| `producao` | Produções bibliográficas e técnicas |
| `projetos` | Projetos de pesquisa/extensão |
| `orientacoes` | Orientações (TCC, mestrado, doutorado…) |
| `iniciacao_cientifica` | Trabalhos de IC |
| `disciplina` | Disciplinas lecionadas (com ementa) |

Itens com ano têm índice de payload em `ano` (filtro `ano_min` / `ano_max`).

---

## Como o ranking é montado

1. **Consulta**: cada tópico tem uma `descricao` (usada na busca), `subtopicos` (usados no reranker) e `disciplinas` (evidência direta). O texto livre vira um "tópico" extra com peso `PESO_TEXTO_LIVRE`.
2. **Busca** em cada coleção no modo `MODO_BUSCA` (`hibrida`, `densa` ou `esparsa`), com `limit` por fonte em `FONTES_ITENS`.
3. **Agregação** ([busca/agregacao.py](sistema_de_busca/busca/agregacao.py)): por professor, média ponderada dos `n` melhores itens de cada tipo (`DECAIMENTO = "log"`, como no nDCG), combinada pelos pesos de cada fonte (`peso_global`, `pesos_internos`) e pelo perfil (`PESO_PROFESSOR`).
4. **Reranking** dos itens dos `FINAL_PROFESSOR_K` melhores professores. Com `RERANK_CONSULTA = "partes"`, cada item é comparado ao nome do tópico e a cada subtópico e fica com a maior nota. Itens abaixo de `MIN_RERANK_RELATIVO` do melhor do mesmo tipo são cortados.
5. **Disciplinas do tema** ([busca/disciplinas_tema.py](sistema_de_busca/busca/disciplinas_tema.py)): quem leciona uma disciplina listada no tópico ganha `BONUS_DISCIPLINA_TEMA` (até o teto).
6. **União dos tópicos** (`UNIAO_TOPICOS = "decaimento"`): o melhor tópico do professor pesa mais, mas a cobertura dos demais também conta.

Todos os parâmetros ficam em [config.py](sistema_de_busca/config.py), comentados.

---

## Estrutura

```
recuperacao/
├── modal_app.py                 deploy da API + front no Modal (GPU, link fixo)
├── frontend/                    questionário do aluno (HTML/JS/CSS), publicado também no GitHub Pages
├── notebooks/
│   ├── colab_api_busca.ipynb    API no Colab (GPU + link público)
│   └── colab_avaliacao.ipynb    avaliação no Colab
└── sistema_de_busca/
    ├── config.py                modelos, coleções, catálogo de TOPICOS e todos os pesos/cortes
    ├── modelo.py                carrega o BGE-M3 e gera embeddings
    ├── database_vetores.py      conexão, criação de coleções, upsert e busca (híbrida/densa/esparsa)
    ├── textos.py                monta o texto de cada item enviado ao modelo
    ├── api.py                   API FastAPI (/recomendar, /topicos, /saude, front em /app)
    ├── comparar_modos.py        compara RERANK_CONSULTA "nome" × "partes"
    ├── indexacao/
    │   ├── execucao.py          indexa a última run da Gold (insere, atualiza, remove)
    │   ├── perfis.py, relacoes.py, tokenizar.py
    │   └── prerankear.py        pré-calcula notas do reranker (cache em disco)
    ├── busca/
    │   ├── service.py           Recomendador: pré-ranking e ranking final
    │   ├── agregacao.py         itens → score por professor
    │   ├── reranking.py         cross-encoder + cortes
    │   ├── cache_rerank.py      cache SQLite das notas do reranker
    │   ├── disciplinas_tema.py  bônus por disciplina do tema
    │   ├── exibicao.py          formatação da resposta
    │   └── diagnostico.py       verificação da configuração
    └── avaliacao/
        ├── avaliar.py           densa × esparsa × híbrida, com e sem reranking
        ├── conjunto.py          conjuntos de referência (TCC/IC → orientador)
        ├── metricas.py          nDCG@k, MRR, Recall@k, Hit@1
        └── consultas_manuais.json
```

---

## Configuração

Variáveis no `.env` da raiz (ver [.env.example](../.env.example)):

| Variável | Uso |
|---|---|
| `QDRANT_URL`, `QDRANT_API_KEY` | Cluster do Qdrant |
| `MINIO_*` | Leitura da Gold na indexação |
| `RERANK_CACHE_PATH` | (opcional) caminho do cache SQLite do reranker; padrão `sistema_de_busca/cache/rerank_scores.sqlite` |
| `LOG_BUSCAS_DIR` | (opcional) pasta onde cada busca da API é registrada em JSON |

Dependências: `pip install -r requirements-busca.txt` e `torch` (CPU ou CUDA, instalado à parte). A primeira execução baixa os modelos do Hugging Face.

---

## Uso

Todos os comandos rodam a partir da **raiz do repositório**.

### 1. Indexar a Gold no Qdrant

```bash
python -m recuperacao.sistema_de_busca.indexacao.execucao
```

Lê a última run da Gold, insere/atualiza só os itens alterados e remove os ausentes (`--exclusao simular` mostra o que seria removido sem apagar).

### 2. (Opcional) Pré-calcular as notas do reranker

```bash
python -m recuperacao.sistema_de_busca.indexacao.prerankear --estimar          # só conta os pares
python -m recuperacao.sistema_de_busca.indexacao.prerankear --topicos "Sistemas Embarcados" --modo partes
```

Sem o cache, o reranker roda na hora (lento em CPU).

### 3. Subir a API

```bash
python -m recuperacao.sistema_de_busca.api
```

Sobe em `http://localhost:8000` (docs em `/docs`, front em `/app`).

| Rota | Descrição |
|---|---|
| `GET /saude` | Verificação simples |
| `GET /topicos` | Catálogo de tópicos (nome, categoria, descrição, disciplinas) |
| `POST /recomendar` | Corpo: `texto` e/ou `topicos` (até 5), `top_k`, `ano_min`, `ano_max`, `incluir_pre_ranking` |

Outras formas de publicar:
- **Modal** (GPU, link fixo): `modal deploy recuperacao/modal_app.py`. Instruções no topo de [modal_app.py](modal_app.py).
- **Colab** (GPU, link temporário): [notebooks/colab_api_busca.ipynb](notebooks/colab_api_busca.ipynb).

### 4. Front-end

[frontend/](frontend/) escolhe a API automaticamente: mesmo endereço quando servido em `/app`, `localhost:8000` quando aberto como arquivo, a API do Modal no GitHub Pages, ou `?api=<url>` na URL. `?debug=1` mostra os scores brutos.

### 5. Avaliar

```bash
python -m recuperacao.sistema_de_busca.avaliacao.avaliar --conjunto tcc --n 150 --k 5
```

Compara busca densa, esparsa e híbrida, cada uma sem e com reranking, nas mesmas consultas (título do TCC/IC → orientador real), com nDCG@k, MRR, Recall@k e Hit@1, e teste de Wilcoxon pareado contra a referência (híbrida + rerank). `--so-pre` avalia só o pré-ranking, sem carregar o reranker.
