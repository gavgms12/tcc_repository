# Pipeline de Dados — Docentes do IESTI/UNIFEI

Projeto de TCC com arquitetura **medalhão** (Bronze → Silver → Gold) para coletar, integrar e estruturar dados dos professores do Instituto de Engenharia de Sistemas e Tecnologia da Informação (IESTI/UNIFEI).

O objetivo é construir uma base de conhecimento sobre os docentes — competências, produções, projetos, orientações e disciplinas — para apoiar a busca de especialistas por embeddings (BGE-M3) indexados no Qdrant.

---

## Visão geral

```
SIGAA · site do IESTI · periódicos de IC                 scriptLattes (CNPq)
        │                                                        │
        ▼                                                        │
  ┌───────────┐   JSON datado em raw/AAAAMMDD/                   │
  │  BRONZE   │ ◄────────────────────────────────────────────────┘
  └─────┬─────┘   (currículos Lattes entram na mesma pasta de data)
        │ lê só a pasta de data mais recente
        ▼
  ┌───────────┐   Parquet: roster, perfis SIGAA e Lattes limpos,
  │  SILVER   │   catálogos de disciplinas e de trabalhos de IC
  └─────┬─────┘
        ▼
  ┌───────────┐   JSON: um perfil por docente (siape) + catálogos
  │   GOLD    │   de produções, projetos, orientações e IC,
  └───────────┘   publicados em runs/<execução>/ e apontados por current.json
        │
        ▼  (próxima etapa) texto do perfil → embeddings → Qdrant
```

Armazenamento: **MinIO** (compatível com S3), um bucket por camada (`bronze`, `silver`, `gold`). Orquestração: **Apache Airflow**, com uma DAG por camada encadeadas por *assets* (a conclusão de uma aciona a seguinte). Tudo roda em Docker Compose.

---

## Fontes

| Fonte | O que fornece |
|-------|---------------|
| [SIGAA — professores do departamento](https://sigaa.unifei.edu.br/sigaa/public/departamento/professores.jsf?id=127) | Nome, siape, portal e link Lattes |
| [SIGAA — componentes curriculares](https://sigaa.unifei.edu.br/sigaa/public/departamento/componentes.jsf?id=127) | Catálogo de disciplinas do instituto (e ementas) |
| SIGAA — página pública de cada docente | Perfil, áreas de interesse, disciplinas ministradas, produção e projetos |
| [Site do IESTI](https://iesti.unifei.edu.br/corpo-docente/) | Nome e id Lattes (o SIGAA nem sempre traz o link) |
| [Periódicos da UNIFEI](https://periodicos.unifei.edu.br/index.php/rtic/issue/archive) | Trabalhos de Iniciação Científica |
| [scriptLattes](https://github.com/jpmenachalco/scriptLattes) | Currículos Lattes (repositório externo) |

---

## Estrutura do repositório

```
tcc_code/
├── bronze/
│   ├── scraping/            # um coletor por fonte (+ utils.py)
│   └── pipeline_bronze.py   # executa todos os coletores
├── silver/
│   ├── merge/               # merge SIGAA + IESTI → roster de identidade
│   ├── integracao/          # scriptLattes e limpeza dos perfis
│   ├── pipeline_silver.py
│   ├── exportar_json.py     # exporta Parquets da Silver para JSON (conferência)
│   └── inspecionar_parquet.py
├── gold/
│   ├── unificar_perfis.py   # perfil unificado por docente + catálogos
│   └── pipeline_gold.py
├── common/                  # texto, id Lattes, config e logging compartilhados
├── storage/minio_storage.py # acesso ao MinIO (classe Camada, chaves datadas da Bronze)
├── dags/                    # DAGs do Airflow (+ assets.py)
├── tests/                   # pytest
├── docker-compose.yml · Dockerfile
├── requirements.txt · requirements-dev.txt · .env.example
└── README.md
```

Cada camada tem seu README (`silver/README.md`, `gold/README.md`) com mais detalhes.

---

## Camadas

### Bronze — coleta bruta

Só web scraping; nenhuma transformação.

| Coletor | Saída (chave lógica) |
|---------|----------------------|
| `scrape_professores_sigaa.py` | `raw/sigaa/professores_sigaa.json` |
| `scrape_sigaa_componentes.py` | `raw/sigaa/componentes_sigaa.json` |
| `scrape_sigaa_docente.py` | `raw/sigaa/docentes_sigaa.json` |
| `scrape_professores_iesti.py` | `raw/iesti_site/professores_iesti_site.json` |
| `scrape_trabalhos_ic.py` | `raw/periodicos/trabalhos_ic_periodicos.json` |

**Dados datados.** Cada coleta é gravada com a data (AAAAMMDD, fuso `America/Sao_Paulo`) na pasta e no nome do arquivo, e nada é sobrescrito entre dias:

```
raw/20261015/sigaa/professores_sigaa_20261015.json
raw/20261015/lattes/json/2146410092995682_20261015.json
```

Rodar de novo no mesmo dia sobrescreve os arquivos daquela data.

**Coletas incrementais.** Para não repetir trabalho:
- *Ementas*: só os componentes ainda não consultados são buscados (a primeira coleta leva ~13 min; as seguintes, segundos).
- *Trabalhos de IC*: artigos já coletados são reaproveitados pela URL.

**Robustez.** A coleta de docentes usa 4 threads e uma falha individual não derruba a execução: ela fica registrada em `falhas` no JSON, e a coleta só é invalidada se mais de 10% dos docentes falharem. A verificação do certificado TLS fica ligada por padrão no SIGAA. O site do IESTI tem a cadeia de certificados incompleta e é coletado sem verificação; o coletor de trabalhos de IC também ainda roda sem verificação por padrão (ambos aceitam `--verify-ssl` para religá-la).

### Silver — dados limpos e integrados

Lê **somente a pasta de data mais recente** da Bronze (ver [Leitura da Bronze](#leitura-da-bronze)).

1. `merge/merge_professores.py` — mescla SIGAA + IESTI (normalização e similaridade de nomes, limiar 0,92) em `professores_unificados.parquet`.
2. `integracao/executar_scriptlattes.py` — roda o scriptLattes para os ids do roster e grava os currículos na Bronze, **na mesma pasta de data que a Silver está lendo**. Os currículos ficam em cache local (`.cache/scriptlattes/cvs`) e expiram após 30 dias.
3. `integracao/limpar_perfis.py` — limpa os perfis e grava **dois Parquets separados** (SIGAA e Lattes), sem mesclá-los. Disciplinas, trabalhos de IC, produções, projetos e orientações passam a ser referenciados por ID (hash do conteúdo, estável entre execuções), com catálogos à parte.

### Gold — produto de dados

`unificar_perfis.py` funde os perfis SIGAA e Lattes em um documento por docente (chave: **siape**). Áreas de especialização são reduzidas às subáreas, tópicos de interesse são unificados sem repetição, e produções, projetos, orientações, disciplinas e trabalhos de IC ficam **só como IDs** no perfil, com o conteúdo em catálogos.

A publicação é atômica: cada execução grava tudo em `runs/<AAAAMMDDTHHMMSSZ>/` e só ao final atualiza `current.json`. A Gold confere se todo ID citado existe no catálogo e falha se mais de 2% das referências estiverem órfãs. Também valida se cada perfil tem texto suficiente para gerar embedding e avisa sobre os que não têm. São mantidas as 3 execuções mais recentes.

---

## Leitura da Bronze

A Silver considera apenas a pasta `raw/AAAAMMDD/` de data mais recente. Se uma fonte necessária não estiver nela, a execução **falha** com uma mensagem indicando qual coleta rodar — não há mistura silenciosa de coletas de dias diferentes.

Consequências práticas:
- Rodar a Bronze completa (script ou DAG) garante todas as fontes na mesma pasta.
- Rodar **um único coletor** num dia novo cria uma pasta de data incompleta, e a Silver passa a exigir que o restante seja coletado nessa data.
- Para reprocessar uma coleta antiga: `BRONZE_DATA=20261013 python silver/pipeline_silver.py`.

Os próprios coletores da Bronze, ao reaproveitar dados já coletados (ementas, IC) ou depender de outra coleta (docentes dependem da lista de professores), usam a última versão de cada chave em qualquer data.

---

## Pré-requisitos

- Python **3.11+**, Docker e Docker Compose.
- Repositório irmão do scriptLattes (para rodar fora do Docker):

```
TCC/
├── tcc_code/        ← este repositório
└── scriptLattes/    ← clonar e instalar separadamente (make install)
```

```bash
cd tcc_code
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt        # runtime + pytest
cp .env.example .env                       # e ajuste usuário/senha do MinIO
```

> Use a venv de `tcc_code/venv` para os scripts deste repositório; a venv do scriptLattes é separada. Dentro do Docker, o scriptLattes já vem na imagem do Airflow.

---

## Como rodar

### Serviços (MinIO + Airflow)

```bash
docker compose up -d
```

| Serviço | URL | Acesso |
|---------|-----|--------|
| Console do MinIO | http://localhost:9011 | `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` do `.env` |
| API S3 do MinIO | http://localhost:9010 | usada pelos scripts |
| Airflow | http://localhost:8085 | usuário `admin`; a senha é gerada na primeira subida: `docker logs tcc-airflow 2>&1 \| grep Password` |

### Pelo Airflow

Dispare a DAG **`bronze_scrape_professores_sigaa`**. Ao terminar, ela aciona `silver_professores_sigaa`, que aciona `gold_professores_sigaa`. Tempos de referência com os caches quentes: Bronze ~3–4 min, Silver ~15 s, Gold ~5 s. As tasks têm novas tentativas automáticas.

### Pela linha de comando

```bash
source venv/bin/activate
python bronze/pipeline_bronze.py --com-ementa
python silver/pipeline_silver.py
python gold/pipeline_gold.py
```

Etapas individuais: `python bronze/scraping/scrape_trabalhos_ic.py`, `python silver/merge/merge_professores.py` etc. — cada script tem `--help`.

### Flags

| Flag | Script | Efeito |
|------|--------|--------|
| `--com-ementa` | `pipeline_bronze.py` | Busca ementas dos componentes ainda não consultados |
| `--limite-docentes N` | `pipeline_bronze.py` | Testa com N docentes |
| `--skip-merge` | `pipeline_silver.py` | Pula o merge SIGAA + IESTI |
| `--skip-lattes` | `pipeline_silver.py` | Pula o scriptLattes |
| `--limite-lattes N` | `pipeline_silver.py` | Baixa só N currículos |
| `--skip-limpeza` | `pipeline_silver.py` | Pula a limpeza dos perfis |

### Variáveis de ambiente

| Variável | Padrão | Uso |
|----------|--------|-----|
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_REGION` | — | Conexão com o MinIO |
| `MINIO_BRONZE_BUCKET`, `MINIO_SILVER_BUCKET`, `MINIO_GOLD_BUCKET` | `bronze`, `silver`, `gold` | Nomes dos buckets |
| `TZ_COLETA` | `America/Sao_Paulo` | Fuso da data das pastas da Bronze |
| `DATA_COLETA` | hoje | Fixa a data de gravação da Bronze |
| `BRONZE_DATA` | pasta mais recente | Fixa a pasta lida pela Silver |
| `LATTES_CACHE_DIAS` | `30` | Validade do cache dos currículos (`0` = nunca expira) |
| `ANO_MINIMO` | ano atual − 10 | Ano inicial das produções e trabalhos de IC |

---

## Saídas no MinIO

| Bucket | Conteúdo |
|--------|----------|
| `bronze` | `raw/AAAAMMDD/<fonte>/<nome>_AAAAMMDD.json`; currículos em `raw/AAAAMMDD/lattes/json/<idLattes>_AAAAMMDD.json` |
| `silver` | `professores_unificados.parquet` — roster (nome, idLattes, siape, urlPortalSigaa) |
| | `perfis_sigaa_limpos.parquet`, `perfis_lattes_limpos.parquet` — perfis limpos por professor |
| | `componentes_curriculares.parquet` — catálogo oficial do IESTI (nome, carga horária, ementa) |
| | `componentes_curriculares_externos.parquet` — disciplinas ministradas fora do IESTI (sem ementa) |
| | `trabalhos_ic_periodicos.parquet` — catálogo de trabalhos de IC com ID |
| `gold` | `current.json` — ponteiro para a execução válida |
| | `runs/<execução>/perfil_professores/<siape>.json` — um perfil por docente |
| | `runs/<execução>/producoes.json`, `projetos.json`, `orientacoes.json`, `disciplinas.json`, `trabalhos_ic.json` — catálogos referenciados pelos perfis |

Números de referência (coleta de 15/10/2026): 43 professores no cadastro (42 com id Lattes), 1249 componentes (837 com ementa; os demais não têm ementa na fonte), 177 trabalhos de IC coletados (46 vinculados a docentes), 729 produções, 125 projetos e 768 orientações no catálogo da Gold.

---

## Testes

```bash
python -m pytest
```

Cobrem as chaves datadas e a leitura da Bronze, os caches (ementas, IC, Lattes), a unificação e publicação da Gold e utilitários comuns, usando um S3 em memória no lugar do MinIO.

---

## Observações

- O SIGAA pode limitar requisições em massa; os coletores usam pausa entre chamadas e retry automático.
- O scriptLattes pode falhar por rate limit do CNPq (`ERR_CONNECTION_RESET`). O cache preserva o que já foi baixado, e a task do Airflow tenta novamente. A saída verbosa do scriptLattes vai para `.cache/scriptlattes/scriptlattes.log`.
- Os dados do MinIO ficam em `./data/minio` (ignorado pelo git).

## Próximos passos

- Limitar as disciplinas a 2022 em diante, para que disciplinas antigas não influenciem o perfil.
- Gerar os documentos textuais e embeddings (BGE-M3) a partir da Gold e indexá-los no Qdrant.
