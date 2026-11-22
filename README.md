# Pipeline de Dados — Docentes do IESTI/UNIFEI

Projeto de TCC com arquitetura **medalhão** (Bronze → Silver → Gold) para coletar, integrar e estruturar dados dos professores do Instituto de Engenharia de Sistemas e Tecnologia da Informação (IESTI/UNIFEI).

O objetivo é construir uma base de conhecimento sobre os docentes — competências, produções, projetos, orientações e disciplinas — pronta para ser consumida por aplicações a partir da camada Gold.

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
```

Armazenamento: **MinIO** (compatível com S3), um bucket por camada (`bronze`, `silver`, `gold`). Orquestração: **Apache Airflow**, com uma DAG por camada encadeadas por *assets* (a conclusão de uma aciona a seguinte), e metadados em **PostgreSQL**. Tudo roda em Docker Compose — detalhes da infraestrutura em [docs/arquitetura.md](docs/arquitetura.md).

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
tcc_repository/
├── src/                         # código do pipeline (pacotes Python)
│   ├── bronze/
│   │   ├── scraping/            # um coletor por fonte (+ utils.py)
│   │   └── pipeline_bronze.py   # executa todos os coletores
│   ├── silver/
│   │   ├── merge/               # merge SIGAA + IESTI → roster de identidade
│   │   ├── integracao/          # scriptLattes e limpeza dos perfis
│   │   └── pipeline_silver.py
│   ├── gold/
│   │   ├── unificar_perfis.py   # perfil unificado por docente + catálogos
│   │   └── pipeline_gold.py
│   ├── common/                  # texto, id Lattes, config e logging compartilhados
│   └── storage/minio_storage.py # acesso ao MinIO (classe Camada, chaves datadas da Bronze)
├── dags/                        # DAGs do Airflow (+ assets.py)
├── scripts/                     # utilitários de conferência (inspecionar/exportar Parquets da Silver)
├── infra/
│   ├── airflow/Dockerfile       # imagem do Airflow com o código e o scriptLattes
│   └── minio/init.sh            # cria buckets e o usuário de serviço do pipeline
├── tests/                       # pytest
├── docs/                        # arquitetura e operação da infraestrutura
├── data/                        # runtime local, fora do git (cache do scriptLattes)
├── docker-compose.yml · .env.example · pyproject.toml
└── requirements.txt · requirements-dev.txt
```

Os pacotes ficam em `src/`, mas os imports não carregam esse prefixo (`from bronze.scraping ...`): a imagem define `PYTHONPATH=/opt/project/src` e, localmente, `pip install -e .` faz o mesmo. Cada camada tem seu README (`src/silver/README.md`, `src/gold/README.md`) com mais detalhes.

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
2. `integracao/executar_scriptlattes.py` — roda o scriptLattes para os ids do roster e grava os currículos na Bronze, **na mesma pasta de data que a Silver está lendo**. Os currículos ficam em cache local (`data/cache/scriptlattes/cvs`) e expiram após 30 dias.
3. `integracao/limpar_perfis.py` — limpa os perfis e grava **dois Parquets separados** (SIGAA e Lattes), sem mesclá-los. Disciplinas, trabalhos de IC, produções, projetos e orientações passam a ser referenciados por ID (hash do conteúdo, estável entre execuções), com catálogos à parte. O catálogo de trabalhos de IC guarda todos os trabalhos coletados, mesmo os sem orientador reconhecido.

### Gold — produto de dados

`unificar_perfis.py` funde os perfis SIGAA e Lattes em um documento por docente (chave: **siape**). Áreas de especialização são reduzidas às subáreas, tópicos de interesse são unificados sem repetição, e produções, projetos, orientações, disciplinas e trabalhos de IC ficam **só como IDs** no perfil, com o conteúdo em catálogos. As iniciações científicas do Lattes saem das orientações e entram nos trabalhos de IC: usam o trabalho coletado de mesmo título, com resumo, ou um registro só com título e ano.

A publicação é atômica: cada execução grava tudo em `runs/<AAAAMMDDTHHMMSSZ>/` e só ao final atualiza `current.json`. A Gold confere se todo ID citado existe no catálogo e falha se mais de 2% das referências estiverem órfãs. Também valida se cada perfil tem texto suficiente para gerar embedding e avisa sobre os que não têm. Fica só a última execução de cada dia, no fuso da coleta, nos 3 dias mais recentes.

---

## Leitura da Bronze

A Silver considera apenas a pasta `raw/AAAAMMDD/` de data mais recente. Se uma fonte necessária não estiver nela, a execução **falha** com uma mensagem indicando qual coleta rodar — não há mistura silenciosa de coletas de dias diferentes.

Consequências práticas:
- Rodar a Bronze completa (script ou DAG) garante todas as fontes na mesma pasta.
- Rodar **um único coletor** num dia novo cria uma pasta de data incompleta, e a Silver passa a exigir que o restante seja coletado nessa data.
- Para reprocessar uma coleta antiga: `BRONZE_DATA=20261013 python -m silver.pipeline_silver`.

Os próprios coletores da Bronze, ao reaproveitar dados já coletados (ementas, IC) ou depender de outra coleta (docentes dependem da lista de professores), usam a última versão de cada chave em qualquer data.

---

## Pré-requisitos

- Docker e Docker Compose (v2.20+).
- Para rodar fora do Docker: Python **3.11+** e, para a etapa do Lattes, o scriptLattes clonado ao lado deste repositório (ou em `SCRIPTLATTES_DIR`). Dentro do Docker ele já vem na imagem do Airflow.

```bash
cp .env.example .env      # troque todos os valores "troque-..." (instruções no arquivo)
mkdir -p data/cache       # cache do scriptLattes, montado no Airflow

# só para rodar scripts/testes fora do Docker:
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt && pip install -e .
```

---

## Como rodar

### Serviços (MinIO + Airflow + Postgres)

```bash
docker compose up -d --build     # primeira vez (constrói a imagem do Airflow)
docker compose up -d             # demais vezes
docker compose ps                # todos devem ficar "healthy"
```

Os serviços reiniciam sozinhos com o Docker (`restart: unless-stopped`). `docker compose down` para tudo sem apagar dados (MinIO, histórico do Airflow e logs ficam em volumes).

| Serviço | URL | Acesso |
|---------|-----|--------|
| Airflow | http://localhost:8085 | usuário `admin`, senha `AIRFLOW_ADMIN_PASSWORD` do `.env` |
| Console do MinIO | http://localhost:9011 | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` do `.env` |
| API S3 do MinIO | http://localhost:9010 | scripts rodados no host (usuário de serviço `MINIO_ACCESS_KEY`) |

As portas só aceitam conexões desta máquina.

### Pelo Airflow

Dispare a DAG **`bronze_scrape_professores_sigaa`**. Ao terminar, ela aciona `silver_professores_sigaa`, que aciona `gold_professores_sigaa`. Tempos de referência com os caches quentes: Bronze ~3–4 min, Silver ~15 s, Gold ~5 s. As tasks têm novas tentativas automáticas.

### Pela linha de comando

Com a stack no ar (os scripts usam o MinIO em `localhost:9010`):

```bash
source venv/bin/activate
python -m bronze.pipeline_bronze --com-ementa
python -m silver.pipeline_silver
python -m gold.pipeline_gold
```

Etapas individuais: `python -m bronze.scraping.scrape_trabalhos_ic`, `python -m silver.merge.merge_professores` etc. — cada script tem `--help`. Conferência da Silver: `python scripts/inspecionar_parquet.py <arquivo.parquet>` e `python scripts/exportar_json.py`.

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
| `SCRIPTLATTES_DIR` | `../scriptLattes` (imagem: `/opt/scriptLattes`) | Instalação do scriptLattes |
| `SCRIPTLATTES_CACHE_DIR` | `data/cache/scriptlattes` | Cache dos currículos baixados |

As variáveis da infraestrutura (credenciais do MinIO, Postgres e segredos do Airflow) estão descritas no `.env.example`.

---

## Saídas no MinIO

| Bucket | Conteúdo |
|--------|----------|
| `bronze` | `raw/AAAAMMDD/<fonte>/<nome>_AAAAMMDD.json`; currículos em `raw/AAAAMMDD/lattes/json/<idLattes>_AAAAMMDD.json` |
| `silver` | `professores_unificados.parquet` — roster (nome, idLattes, siape, urlPortalSigaa) |
| | `perfis_sigaa_limpos.parquet`, `perfis_lattes_limpos.parquet` — perfis limpos por professor |
| | `componentes_curriculares.parquet` — catálogo oficial do IESTI (nome, carga horária, ementa) |
| | `componentes_curriculares_externos.parquet` — disciplinas ministradas fora do IESTI (sem ementa) |
| | `trabalhos_ic_periodicos.parquet` — catálogo de todos os trabalhos de IC coletados, com ID |
| `gold` | `current.json` — ponteiro para a execução válida |
| | `runs/<execução>/perfil_professores/<siape>.json` — um perfil por docente |
| | `runs/<execução>/producoes.json`, `projetos.json`, `orientacoes.json`, `disciplinas.json`, `trabalhos_ic.json` — catálogos referenciados pelos perfis |

Números de referência (coleta de 15/10/2026): 43 professores no cadastro (42 com id Lattes), 1249 componentes (837 com ementa; os demais não têm ementa na fonte), 177 trabalhos de IC coletados (46 vinculados a docentes), 729 produções, 125 projetos e 768 orientações no catálogo da Gold.

---

## Testes

```bash
python -m pytest     # não precisa da stack no ar
```

Cobrem as chaves datadas e a leitura da Bronze, os caches (ementas, IC, Lattes), a unificação e publicação da Gold e utilitários comuns, usando um S3 em memória no lugar do MinIO.

---

## Observações

- O SIGAA pode limitar requisições em massa; os coletores usam pausa entre chamadas e retry automático.
- O scriptLattes pode falhar por rate limit do CNPq (`ERR_CONNECTION_RESET`). O cache preserva o que já foi baixado, e a task do Airflow tenta novamente. A saída verbosa do scriptLattes vai para `data/cache/scriptlattes/scriptlattes.log`.
- Os dados do MinIO ficam no volume Docker `tcc_minio_data`, não numa pasta do repositório.

## Próximos passos

- Limitar as disciplinas a 2022 em diante, para que disciplinas antigas não influenciem o perfil. Os anos já chegam à Gold em `disciplinasPorAno` de cada perfil; falta aplicar o filtro.
