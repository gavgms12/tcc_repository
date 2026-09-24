# Pipeline de Dados — Docentes do IESTI/UNIFEI

Projeto de TCC com arquitetura **medalhão** para coletar, integrar e estruturar dados de professores do Instituto de Engenharia de Sistemas e Tecnologia da Informação (IESTI/UNIFEI).

O objetivo é construir uma base de conhecimento sobre os docentes — competências, produções, projetos e disciplinas — para, no futuro, apoiar buscas por especialistas (ex.: com embeddings na camada Gold).

---

## Visão geral do fluxo

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

## Estrutura de pastas

```
tcc_code/
├── bronze/
│   ├── scraping/            # coleta bruta: SIGAA, IESTI, periódicos, docentes, componentes
│   ├── lattes/              # estrutura de saída da coleta do currículo Lattes
│   ├── pipeline_bronze.py   # orquestração da camada Bronze
│   └── requirements.txt
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

> A camada Bronze fica restrita ao web scraping e à coleta bruta. A camada Silver faz o merge de identidade e a limpeza de cada fonte (SIGAA e Lattes) separadamente. A Gold só lê Parquets da Silver e unifica os perfis por professor.

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
└── scriptLattes/    ← clonar e instalar separadamente
```

No scriptLattes, criar a venv e instalar:

```bash
cd ../scriptLattes
make install
```

O pipeline Silver gera uma configuração temporária e isolada para o
scriptLattes. Ela não altera os exemplos nem as configurações existentes em
`Documentos/scriptLattes`; os JSONs gerados são enviados para o MinIO ao fim da
execução.

---

## Como rodar

### Opção 1 — Pipeline completo (recomendado)

```bash
cd tcc_code
source venv/bin/activate
python bronze/pipeline_bronze.py
python silver/pipeline_silver.py
python gold/pipeline_gold.py
```

Isso executa, em ordem: coleta Bronze → JSONs no MinIO → merge de identidade →
coleta Lattes (JSONs em `bronze/raw/lattes/json/`) → limpeza SIGAA/Lattes/IC
(Parquets na Silver) → unificação dos perfis (Parquet na Gold).

Para executar apenas a gravação Parquet a partir dos JSONs Bronze já existentes:

```bash
python silver/pipeline_silver.py
```

### Opção 2 — Etapas individuais

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
