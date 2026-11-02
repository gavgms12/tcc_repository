#rodar windows senha docker -> docker logs tcc-airflow 2>&1 | Select-String "Password"

# Pipeline de Dados — Docentes do IESTI/UNIFEI

Projeto de TCC com arquitetura **medalhão** (Bronze → Silver → Gold) para coletar, integrar e estruturar dados dos professores do Instituto de Engenharia de Sistemas e Tecnologia da Informação (IESTI/UNIFEI).

O objetivo é construir uma base de conhecimento sobre os docentes — competências, produções, projetos, orientações e disciplinas — para apoiar a busca de especialistas por embeddings (BGE-M3) indexados no Qdrant.

---

## Visão geral

```
SIGAA + site IESTI + periódicos
              │
              ▼
        ┌──────────┐
        │  BRONZE  │  coleta bruta
        └──────────┘
              │
              ▼
        ┌──────────┐     scriptLattes (CNPq)
        │  SILVER  │ ───────────────────────► currículos Lattes
        │ merge e  │
        │ limpeza  │
        │por fonte │
        └──────────┘
              │
              ▼
        ┌──────────┐
        │   GOLD   │  unificação SIGAA + Lattes
        └──────────┘
```

---

## O que já está implementado

### Bronze — coleta bruta

| Etapa | Script | O que faz |
|-------|--------|-----------|
| Professores SIGAA | `bronze/scraping/scrape_professores_sigaa.py` | Nome, siape, portal e link Lattes |
| Componentes curriculares | `bronze/scraping/scrape_sigaa_componentes.py` | Catálogo de disciplinas do instituto |
| Detalhes por docente | `bronze/scraping/scrape_sigaa_docente.py` | Perfil, disciplinas, produção e projetos no SIGAA |
| Professores IESTI | `bronze/scraping/scrape_professores_iesti.py` | Nome e id Lattes do site do instituto |
| Trabalhos de IC | `bronze/scraping/scrape_trabalhos_ic.py` | Catálogo de trabalhos de iniciação científica |
| Pipeline | `bronze/pipeline_bronze.py` | Executa a coleta bruta |

**Fontes de dados:**
- [SIGAA — professores do departamento](https://sigaa.unifei.edu.br/sigaa/public/departamento/professores.jsf?id=127)
- [SIGAA — componentes curriculares](https://sigaa.unifei.edu.br/sigaa/public/departamento/componentes.jsf?id=127)
- [SIGAA — páginas públicas por docente](https://sigaa.unifei.edu.br/sigaa/public/docente/portal.jsf)
- Site do IESTI
- Currículos Lattes via [scriptLattes](https://github.com/jpmenachalco/scriptLattes) (repositório externo)
- [Site de periódicos UNIFEI](https://periodicos.unifei.edu.br/index.php/rtic/issue/archive)


### Silver — limpeza por fonte

| Script | O que faz |
|--------|-----------|
| `silver/01_merge/merge_professores.py` | Mescla identidade SIGAA + IESTI (nome, idLattes, siape) em Parquet (`identidade_professores.parquet`) |
| `silver/02_integracao/executar_scriptlattes.py` | Roda o scriptLattes e envia os currículos brutos para a Bronze |
| `silver/03_limpeza/limpar_perfil_sigaa.py` | Limpa o perfil SIGAA: remove contato e o link de Lattes duplicado, remove atividades de extensão, reduz disciplinas a IDs do catálogo de componentes, projetos de pesquisa a nome/área, e produção docente a título+ano a partir de 2016 (título extraído por IA) |
| `silver/03_limpeza/limpar_perfil_lattes.py` | Limpa o currículo Lattes (foco em embeddings bge-m3): resumo, competências, títulos de produções/projetos/orientações |
| `silver/03_limpeza/limpar_trabalhos_ic.py` | Normaliza o catálogo de trabalhos de IC/periódicos (sem vincular a professor ainda) |
| `silver/pipeline_silver.py` | Orquestra as etapas acima |

A Silver **não** une SIGAA com Lattes — cada fonte é limpa e gravada separadamente. A unificação por professor é responsabilidade exclusiva da Gold.

### Gold — perfil unificado

| Script | O que faz |
|--------|-----------|
| `gold/01_unificacao/unificar_perfis.py` | Lê só os Parquets já limpos da Silver, vincula os trabalhos de IC ao professor orientador (por similaridade de nome) e grava o perfil unificado por professor |
| `gold/pipeline_gold.py` | Orquestra a etapa acima |

A Gold não lê nada da Bronze e não faz limpeza — só unifica o que a Silver já preparou. Cada perfil unificado contém: resumo, competências (áreas, linhas de pesquisa, palavras-chave), títulos de produções/projetos/orientações (Lattes e SIGAA), IDs de disciplinas ministradas e IDs de trabalhos de IC/periódicos orientados.

---

## Estrutura do repositório

```
tcc_code/
├── bronze/
│   ├── scraping/            # um coletor por fonte (+ utils.py)
│   └── pipeline_bronze.py   # executa todos os coletores
├── silver/
│   ├── 01_merge/            # merge SIGAA + IESTI e geração da lista para Lattes
│   ├── 02_integracao/       # coleta dos currículos Lattes via scriptLattes
│   ├── 03_limpeza/          # limpeza SIGAA e Lattes, cada fonte separada
│   ├── pipeline_silver.py   # orquestração da camada Silver
│   ├── README.md
│   └── ...
├── gold/
│   ├── 01_unificacao/       # unifica os perfis SIGAA + Lattes já limpos na Silver
│   ├── pipeline_gold.py     # orquestração da camada Gold
│   └── README.md
├── data/
│   ├── bronze/
│   │   ├── raw/
│   │   │   ├── iesti_site/
│   │   │   ├── sigaa/
│   │   │   └── periodicos/
│   │   ├── lattes/
│   │   ├── merged/
│   │   └── lista/
│   └── silver/
│       ├── base/
│       ├── lista/
│       ├── docentes/
│       └── README.md
└── README.md
```

<<<<<<< HEAD
> A camada Bronze fica restrita ao web scraping e à coleta bruta. A camada Silver faz o merge de identidade e a limpeza de cada fonte (SIGAA e Lattes) separadamente. A Gold só lê Parquets da Silver e unifica os perfis por professor.
=======
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
- Para reprocessar uma coleta antiga: `BRONZE_DATA=20261013 python silver/pipeline_silver.py`.

Os próprios coletores da Bronze, ao reaproveitar dados já coletados (ementas, IC) ou depender de outra coleta (docentes dependem da lista de professores), usam a última versão de cada chave em qualquer data.
>>>>>>> 3a374352c7d7ea4c352fb30ba1ec5f5e27e94a1e

---

## Pré-requisitos

1. **Python 3.10+**
2. Ambiente virtual e dependências Python (Bronze/Silver):

```bash
cd tcc_code
python -m venv venv
source venv/bin/activate   # Linux/macOS; no Windows: venv\Scripts\activate
pip install -r bronze/requirements.txt
```

3. **MinIO**: copie o arquivo de configuração e informe o endpoint e as
credenciais do Data Lake.

```bash
cp .env.example .env
```

Os coletores gravam JSON diretamente no bucket `bronze` (sem arquivos em
`data/`). A Silver lê esses objetos, limpa cada fonte separadamente e grava os
Parquets no bucket `silver`. A Gold lê só esses Parquets e grava o perfil
unificado (`professores_unificados.parquet`) no bucket `gold` — por padrão
`MINIO_GOLD_BUCKET=gold`, configurável no `.env` como os demais buckets.
MongoDB não faz parte desse fluxo.

Para a extração de títulos por IA na limpeza da produção docente do SIGAA,
configure `HF_TOKEN` (token gratuito da Hugging Face) no `.env`; sem ele, o
pipeline usa uma extração por regex como alternativa (ver
`silver/03_limpeza/ia_titulos.py`).

> Use a venv em `tcc_code/venv` para os scripts deste repositório. A venv do **scriptLattes** é separada e não inclui todas as dependências do Bronze (ex.: `requests`).

4. **scriptLattes** (repositório irmão):

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
cd tcc_code
source venv/bin/activate
python bronze/pipeline_bronze.py
python silver/pipeline_silver.py
python gold/pipeline_gold.py
```

<<<<<<< HEAD
Isso executa, em ordem: coleta Bronze → JSONs no MinIO → merge de identidade →
coleta Lattes (JSONs em `bronze/raw/lattes/json/`) → limpeza SIGAA/Lattes/IC
(Parquets na Silver) → unificação dos perfis (Parquet na Gold).
=======
Esse comando sobe só o Airflow, que usa o MinIO antigo (container `tcc_minio`, portas 9000 e 9001, conectado à rede `tcc_repository_default` com o alias `tcc-minio`). Em uma instalação nova, sem esse container, suba o MinIO do projeto com `docker compose --profile minio-local up -d`, nas portas da tabela abaixo. Não mantenha os dois ligados, porque o nome `tcc-minio` passaria a apontar para dois servidores.

| Serviço | URL | Acesso |
|---------|-----|--------|
| Console do MinIO | http://localhost:9011 | `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` do `.env` |
| API S3 do MinIO | http://localhost:9010 | usada pelos scripts |
| Airflow | http://localhost:8085 | usuário `admin`; a senha é gerada na primeira subida: `docker logs tcc-airflow 2>&1 \| grep Password` |
>>>>>>> 3a374352c7d7ea4c352fb30ba1ec5f5e27e94a1e

Para executar apenas a gravação Parquet a partir dos JSONs Bronze já existentes:

```bash
source venv/bin/activate
python bronze/pipeline_bronze.py --com-ementa
python silver/pipeline_silver.py
```

<<<<<<< HEAD
### Opção 2 — Etapas individuais
=======
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
| | `trabalhos_ic_periodicos.parquet` — catálogo de todos os trabalhos de IC coletados, com ID |
| `gold` | `current.json` — ponteiro para a execução válida |
| | `runs/<execução>/perfil_professores/<siape>.json` — um perfil por docente |
| | `runs/<execução>/producoes.json`, `projetos.json`, `orientacoes.json`, `disciplinas.json`, `trabalhos_ic.json` — catálogos referenciados pelos perfis |

Números de referência (coleta de 15/10/2026): 43 professores no cadastro (42 com id Lattes), 1249 componentes (837 com ementa; os demais não têm ementa na fonte), 177 trabalhos de IC coletados (46 vinculados a docentes), 729 produções, 125 projetos e 768 orientações no catálogo da Gold.

---

## Testes
>>>>>>> 3a374352c7d7ea4c352fb30ba1ec5f5e27e94a1e

```bash
cd tcc_code

# 1. Coletar professores e dados do SIGAA
python bronze/scraping/scrape_professores_sigaa.py
python bronze/scraping/scrape_sigaa_componentes.py
python bronze/scraping/scrape_sigaa_docente.py

# 2. Coletar site IESTI e outros dados brutos
python bronze/scraping/scrape_professores_iesti.py
python bronze/scraping/scrape_trabalhos_ic.py
python silver/01_merge/merge_professores.py
```

---

## Flags úteis

| Flag | Onde | Efeito |
|------|------|--------|
| `--skip-scraping` | `pipeline_bronze.py` | Usa dados brutos já coletados |
| `--skip-lattes` | `pipeline_silver.py` | Pula a coleta de currículos pelo scriptLattes |
| `--limite-lattes N` | `pipeline_silver.py` | Testa a coleta de apenas N currículos |
| `--skip-limpeza-sigaa` | `pipeline_silver.py` | Pula a limpeza dos perfis SIGAA |
| `--skip-limpeza-lattes` | `pipeline_silver.py` | Pula a limpeza dos currículos Lattes |
| `--skip-limpeza-ic` | `pipeline_silver.py` | Pula a limpeza do catálogo de trabalhos de IC/periódicos |
| `--limite-docentes N` | `pipeline_bronze.py` | Testa com N docentes |
| `--com-ementa` | `pipeline_bronze.py` | Busca ementa de todos os componentes (lento) |
| `--limite N` | `scrape_sigaa_docente.py` | Limita docentes coletados |

---

## Principais saídas no MinIO

| Bucket / chave | Conteúdo |
|---------|----------|
| `bronze/raw/sigaa/professores_sigaa.json` | Lista básica (nome, siape, Lattes) |
| `bronze/raw/sigaa/componentes_sigaa.json` | Catálogo de disciplinas do instituto |
| `bronze/raw/sigaa/docentes_sigaa.json` | Perfil completo por docente no SIGAA |
| `bronze/raw/periodicos/trabalhos_ic_periodicos.json` | Catálogo de trabalhos de iniciação científica |
| `bronze/raw/lattes/json/{id_lattes}.json` | Currículo bruto individual gerado pelo scriptLattes |
| `silver/identidade_professores.parquet` | Identidade mesclada SIGAA + IESTI (nome, idLattes, siape) — não é um perfil |
| `silver/perfil_sigaa_limpo.parquet` | Perfil SIGAA limpo por siape (sem contato, sem extensão, disciplinas por ID, projetos e produção docente podados) |
| `silver/perfil_lattes_limpo.parquet` | Perfil Lattes limpo por idLattes (resumo, competências, produções/projetos/orientações) |
| `silver/trabalhos_ic_periodicos.parquet` | Catálogo de trabalhos de IC/periódicos limpo, com ID (ainda sem vínculo a professor) |
| `silver/componentes_curriculares.parquet` | Catálogo de disciplinas por idSigaa — estende `componentes_sigaa.json` com disciplinas de outros departamentos/pós-graduação que os docentes lecionam e que não constam no catálogo oficial do departamento |
| `gold/professores_unificados.parquet` | Perfil unificado por professor (resumo, competências, produções, disciplinas por ID, IC por ID) — única saída da Gold |

---

## Números atuais (referência)

- **46** professores no cadastro mesclado
- **44** com id Lattes válido
- **43** com siape no SIGAA
- **~1245** componentes curriculares catalogados
- Dados SIGAA complementam o Lattes (formação, áreas de interesse, disciplinas ministradas, projetos)

---

## Observações

- O SIGAA pode limitar requisições em massa; os scripts usam pausa entre chamadas e retry automático.
- O scriptLattes pode falhar por rate limit do CNPq (`ERR_CONNECTION_RESET`); é possível retomar depois — o cache evita baixar de novo o que já foi obtido.
- A primeira execução de `--buscar-ementa-vinculadas` demora mais (~12 min); nas próximas, as ementas já ficam em cache no `componentes.json`.

---

## Próximos passos (planejado)
- Limitar buscar as disciplinas de 2022 pra frente para que as disciplinas mais antigas não enfluenciem
- Gold: gerar embeddings (bge-m3) a partir do perfil unificado e busca por especialistas
