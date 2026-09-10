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
        │ integração│
        └──────────┘
              │
              ▼
        ┌──────────┐
        │   GOLD   │  (futuro) busca / embeddings
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


### Silver — dados tratados

| Script | O que faz |
|--------|-----------|
| `silver/01_merge/merge_professores.py` | Mescla identidade SIGAA + IESTI (nome, idLattes, siape) em Parquet |
| `silver/02_integracao/executar_scriptlattes.py` | Roda o scriptLattes e envia os currículos brutos para a Bronze |
| `silver/02_integracao/unificar_perfis.py` | Limpa os perfis SIGAA e Lattes (foco em embeddings bge-m3), unifica por idLattes, reduz disciplinas a IDs do catálogo de componentes e trabalhos de IC/periódicos a IDs de um catálogo à parte |
| `silver/pipeline_silver.py` | Orquestra as três etapas acima |

Cada perfil unificado contém: resumo, competências (áreas, linhas de pesquisa, palavras-chave), títulos de produções/projetos/orientações, IDs de disciplinas ministradas e IDs de trabalhos de IC/periódicos orientados.

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
│   ├── 02_integracao/       # unificação com Lattes, vínculos e limpeza final
│   ├── pipeline_silver.py   # orquestração da camada Silver
│   ├── README.md
│   └── ...
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

> A camada Bronze fica restrita ao web scraping e à coleta bruta. A camada Silver assume os passos de merge, enriquecimento e limpeza. A Gold permanece fora do escopo neste momento.

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
`data/`). A Silver lê esses objetos e grava `professores_unificados.parquet` no
bucket `silver`. MongoDB não faz parte desse fluxo.

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
```

Isso executa, em ordem: coleta Bronze → JSONs no MinIO → merge de professores
→ Parquet no bucket Silver → coleta Lattes → JSONs em
`bronze/raw/lattes/json/`.

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
| `--skip-unificacao` | `pipeline_silver.py` | Pula a limpeza/unificação dos perfis SIGAA + Lattes |
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
| `silver/professores_unificados.parquet` | Perfil unificado por professor (resumo, competências, produções, disciplinas por ID, IC por ID) |
| `silver/trabalhos_ic_periodicos.parquet` | Catálogo de trabalhos de IC/periódicos com ID, referenciados pelos professores |
| `silver/componentes_curriculares.parquet` | Catálogo de disciplinas por idSigaa — estende `componentes_sigaa.json` com disciplinas de outros departamentos/pós-graduação que os docentes lecionam e que não constam no catálogo oficial do departamento |

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
- Merge Silver: integrar dados SIGAA (disciplinas, perfil, ics) com os perfis Lattes
- Camada Gold: embeddings e busca por especialistas
