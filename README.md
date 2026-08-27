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
| `silver/transformar_lattes.py` | Limpa os JSONs do Lattes e gera um perfil estruturado por docente |
| `silver/unir_lattes_sigaa.py` | Unifica perfis Silver com dados SIGAA (disciplinas, TCC, IC) |
| `silver/pipeline_silver.py` | Faz merge, gera a lista Lattes, coleta os currículos e integra os dados |

Cada arquivo Silver contém: dados do docente, competências, produções, projetos, orientações e linhagem acadêmica.

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

> Use a venv em `tcc_code/venv` para os scripts deste repositório. A venv do **scriptLattes** é separada e não inclui todas as dependências do Bronze (ex.: `requests`).

3. **scriptLattes** (repositório irmão, fora deste projeto):

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

O pipeline usa o config em `scriptLattes/exemplo/teste-02.config`, apontando para os arquivos em `tcc_code/data/bronze/`.

---

## Como rodar

### Opção 1 — Pipeline completo (recomendado)

```bash
cd tcc_code
source venv/bin/activate
python bronze/pipeline_bronze.py
python silver/pipeline_silver.py
```

Isso executa, em ordem: coleta Bronze → merge → geração da lista Lattes → download dos currículos → vínculos e integração Silver.

Para atualizar somente os dados coletados, sem baixar currículos:

```bash
python bronze/pipeline_bronze.py
python silver/pipeline_silver.py --skip-lattes --skip-integracao
```

### Opção 2 — Etapas individuais

```bash
cd tcc_code

# 1. Coletar professores e dados do SIGAA
python bronze/scraping/scrape_professores_sigaa.py
python bronze/scraping/scrape_sigaa_componentes.py
python bronze/scraping/scrape_sigaa_docente.py

# 2. Coletar site IESTI e mesclar fontes
python bronze/scraping/scrape_professores_iesti.py
python bronze/scraping/scrape_trabalhos_ic.py
python silver/01_merge/merge_professores.py
python silver/01_merge/gerar_lista_scriptlattes.py


# 3. Baixar currículos e integrar os dados
python silver/pipeline_silver.py --skip-merge --skip-lista
```

---

## Flags úteis

| Flag | Onde | Efeito |
|------|------|--------|
| `--skip-lattes` | `pipeline_silver.py` | Pula o download dos currículos |
| `--skip-integracao` | `pipeline_silver.py` | Pula vínculos e integração final |
| `--skip-scraping` | `pipeline_bronze.py` | Usa dados brutos já coletados |
| `--limite-docentes N` | `pipeline_bronze.py` | Testa com N docentes |
| `--com-ementa` | `pipeline_bronze.py` | Busca ementa de todos os componentes (lento) |
| `--limite N` | `scrape_sigaa_docente.py` | Limita docentes coletados |

---

## Principais saídas

| Arquivo | Conteúdo |
|---------|----------|
| `data/bronze/raw/sigaa/professores_sigaa.json` | Lista básica (nome, siape, Lattes) |
| `data/bronze/raw/sigaa/componentes_sigaa.json` | Catálogo de disciplinas do instituto |
| `data/bronze/raw/sigaa/docentes_sigaa.json` | Perfil completo por docente no SIGAA |
| `data/bronze/raw/sigaa/vinculos_professor_disciplina.json` | Professor ↔ disciplinas + ementa |
| `data/bronze/raw/periodicos/trabalhos_ic_periodicos.json` | Catálogo de trabalhos de iniciação científica |
| `data/silver/professores_unificados.json` | Cadastro unificado Lattes + SIGAA |
| `data/bronze/merged/professores_sigaa_iesti_merged.json` | Cadastro unificado (SIGAA + IESTI) |
| `data/bronze/lista/professores_lattes.list` | Lista de entrada do scriptLattes |
| `data/bronze/relatorio_qualidade.txt` | Resumo de cobertura e lacunas |
| `data/silver/docentes/{id_lattes}.json` | Perfil limpo a partir do Lattes |

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
