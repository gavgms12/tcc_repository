# Pipeline de Dados — Docentes do IESTI/UNIFEI

Projeto de TCC com arquitetura **medalhão** para coletar, integrar e estruturar dados de professores do Instituto de Engenharia de Sistemas e Tecnologia da Informação (IESTI/UNIFEI).

O objetivo é construir uma base de conhecimento sobre os docentes — competências, produções, projetos e disciplinas — para, no futuro, apoiar buscas por especialistas (ex.: com embeddings na camada Gold).

---

## Visão geral do fluxo

```
SIGAA + site IESTI          scriptLattes (CNPq)
       │                            │
       ▼                            ▼
   ┌─────────┐                 ┌─────────┐
   │ BRONZE  │ ── merge ──►    │ BRONZE  │
   │ (SIGAA) │                 │(Lattes) │
   └─────────┘                 └─────────┘
       │                            │
       └──────────┬─────────────────┘
                  ▼
            ┌──────────┐
            │  SILVER  │  perfis limpos por docente
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
| Professores SIGAA | `bronze/scrape_professores_sigaa.py` | Nome, siape, portal e link Lattes |
| Componentes curriculares | `bronze/scrape_sigaa_componentes.py` | Catálogo de disciplinas do instituto (~1245) |
| Detalhes por docente | `bronze/scrape_sigaa_docente.py` | Perfil, disciplinas, produção e projetos no SIGAA |
| Professores IESTI | `bronze/scrape_professores_iesti.py` | Nome e id Lattes do site do instituto |
| Trabalhos Iniciação Científica | `bronze/scrape_trabalhos_ic.py` | Périodicos de Iniciação Científica|
| Merge | `bronze/merge_professores.py` | Unifica SIGAA + IESTI (fuzzy match de nomes) |
| Vínculos disciplinas | `bronze/vincular_disciplinas.py` | Liga professores às disciplinas + ementa |
| Vínculos iniciação científica| `bronze/vincular_ics.py` | Liga professores às iniciações científica + palavras-chaves |
| Lista Lattes | `bronze/lista_lattes/gerar_lista_scriptlattes.py` | Gera `.list` para o scriptLattes |
| Pipeline | `bronze/pipeline_bronze.py` | Executa todas as etapas acima em sequência |

**Fontes de dados:**
- [SIGAA — professores do departamento](https://sigaa.unifei.edu.br/sigaa/public/departamento/professores.jsf?id=127)
- [SIGAA — componentes curriculares](https://sigaa.unifei.edu.br/sigaa/public/departamento/componentes.jsf?id=127)
- [SIGAA — páginas públicas por docente](https://sigaa.unifei.edu.br/sigaa/public/docente/portal.jsf)
- Site do IESTI
- Currículos Lattes via [scriptLattes](https://github.com/jpmenachalco/scriptLattes) (repositório externo)
- - [Site de periódicos UNIFEI](https://periodicos.unifei.edu.br/index.php/rtic/issue/archive)


### Silver — dados tratados

| Script | O que faz |
|--------|-----------|
| `silver/transformar_lattes.py` | Limpa os JSONs do Lattes e gera um perfil estruturado por docente |

Cada arquivo Silver contém: dados do docente, competências, produções, projetos, orientações e linhagem acadêmica.

---

## Estrutura de pastas

```
tcc_code/
├── bronze/                  # scripts de scraping e integração
├── silver/                  # scripts de transformação
├── data/
│   ├── bronze/
│   │   ├── sigaa/           # professores, componentes, docentes, vínculos
│   │   ├── iesti_site/
│   │   ├── merged/          # cadastro unificado
│   │   ├── lista/           # professores.list
│   │   ├── periodicos/      # trabalhos iniciação científica
│   │   └── lattes/json/     # currículos baixados
│   └── silver/
│       └── docentes/        # um JSON por id Lattes
└── README.md
```

> Os dados em `data/` não vão para o Git (estão no `.gitignore`). Apenas a estrutura de pastas é versionada.

---

## Pré-requisitos

1. **Python 3.10+**
2. Dependências Python:

```bash
cd bronze
pip install -r requirements.txt
```

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
cd bronze
python pipeline_bronze.py
```

Isso executa, em ordem: scraping SIGAA → componentes → docentes → IESTI → merge → vínculos → lista Lattes → download dos currículos.

Para atualizar só scraping/merge, sem baixar Lattes:

```bash
python pipeline_bronze.py --skip-lattes
```

### Opção 2 — Etapas individuais

```bash
cd bronze

# 1. Coletar professores e dados do SIGAA
python scrape_professores_sigaa.py
python scrape_sigaa_componentes.py
python scrape_sigaa_docente.py

# 2. Coletar site IESTI e mesclar fontes
python scrape_professores_iesti.py
python scrape_trabalhos_ic.py
python merge_professores.py
python vincular_disciplinas.py --buscar-ementa-vinculadas
python vincular_ics.py --buscar-ics-vinculada


# 3. Gerar lista e baixar currículos (no scriptLattes)
python lista_lattes/gerar_lista_scriptlattes.py
```

### Silver

Após ter os JSONs do Lattes na Bronze:

```bash
cd silver
python transformar_lattes.py
```

---

## Flags úteis

| Flag | Onde | Efeito |
|------|------|--------|
| `--skip-lattes` | `pipeline_bronze.py` | Pula o download dos currículos |
| `--skip-scraping` | `pipeline_bronze.py` | Usa dados já coletados |
| `--limite-docentes N` | `pipeline_bronze.py` | Testa com N docentes |
| `--com-ementa` | `pipeline_bronze.py` | Busca ementa de todos os componentes (lento) |
| `--limite N` | `scrape_sigaa_docente.py` | Limita docentes coletados |

---

## Principais saídas

| Arquivo | Conteúdo |
|---------|----------|
| `data/bronze/sigaa/professores.json` | Lista básica (nome, siape, Lattes) |
| `data/bronze/sigaa/componentes.json` | Catálogo de disciplinas do instituto |
| `data/bronze/sigaa/docentes.json` | Perfil completo por docente no SIGAA |
| `data/bronze/sigaa/vinculos_professor_disciplina.json` | Professor ↔ disciplinas + ementa |
| `data/bronze/periodicos/trabalhos.json` | Catálogo de trabalhos de iniciação cientifica |
| `data/bronze/merged/professores.json` | Cadastro unificado (SIGAA + IESTI + vínculos) |
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
