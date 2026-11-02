# Recuperação

A Recuperação indexa os dados da Gold no Qdrant e recomenda professores
orientadores a partir dos tópicos escolhidos pelo aluno. A busca combina
embeddings densos e esparsos do BGE-M3 e reordena os resultados com o
reranker `bge-reranker-v2-m3`.

## Organização

- `sistema_de_busca/config.py` — modelos, coleções, tópicos, limites de busca e pesos de cada fonte
- `sistema_de_busca/textos.py` — monta o texto de cada objeto que vai para o modelo (em minúsculas)
- `sistema_de_busca/modelo.py` — carrega o BGE-M3 e gera os embeddings densos e esparsos
- `sistema_de_busca/database_vetores.py` — conexão com o Qdrant, criação de coleções, upsert e busca híbrida
- `sistema_de_busca/indexacao/` — leitura da Gold, relação professor ↔ objeto e indexação
- `sistema_de_busca/busca/` — pré-ranking, reranking, união dos tópicos e exibição
- `sistema_de_busca/teste.py` — exemplo de consulta com saída de diagnóstico
- `test/` — notebooks de experimentos com o BGE-M3

## Coleções

| Coleção | Conteúdo | Filtro por ano |
|---------|----------|----------------|
| `perfil_professores` | resumo, áreas de especialização e tópicos de interesse | não |
| `producao` | títulos de livros, artigos, capítulos e trabalhos em congresso | sim |
| `projetos` | título e descrição de projetos de pesquisa, extensão e desenvolvimento | sim |
| `orientacoes` | títulos das orientações | sim |
| `iniciacao_cientifica` | título, resumo e palavras-chave dos trabalhos de IC | sim |
| `disciplina` | prevista no `config.py`, ainda não indexada | não |

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

1. **Busca híbrida** — busca densa e esparsa em cada coleção, unidas por RRF (`limit` resultados)
2. **Pré-ranking** — cada professor recebe a média dos seus `n` melhores itens por coleção (posições vazias contam como 0), multiplicada por `peso_interno`. As coleções são combinadas por `peso_global`, e o perfil vale `PESO_PROFESSOR`

Depois, para todos os tópicos juntos:

3. **União** — média dos scores entre os tópicos (tópico ausente conta como 0). Só seguem professores com pelo menos um item encontrado, e o corte é em `FINAL_PROFESSOR_K`
4. **Reranking** — cada item é comparado com o tópico que o encontrou. Itens abaixo de `MIN_RERANK` são descartados, e professores sem nenhum item restante saem do ranking
5. **Resultado** — os `top_k` professores, com o score de cada tópico e os itens mais relevantes de cada coleção

## Como rodar

Variáveis no `.env`: `QDRANT_URL`, `QDRANT_API_KEY` e as credenciais do MinIO.

```powershell
# indexar ou atualizar as coleções
python -m recuperacao.sistema_de_busca.indexacao.execucao

# contar tokens dos textos (verifica cortes do modelo e do reranker)
python -m recuperacao.sistema_de_busca.indexacao.tokenizar

# rodar a consulta de exemplo
python -m recuperacao.sistema_de_busca.teste
```

```python
rec = Recomendador(client, modelo, reranker)
topicos = {t: config.TOPICOS[t] for t in ["Compiladores", "Grafos"]}
resultado = rec.recomendar(topicos, top_k=8, ano_min=2015, debug=True)
```

Com `debug=True`, a busca mostra o cálculo do pré-ranking e do reranking de
cada professor.

## Observações

- O reranker roda na CPU se o PyTorch não tiver CUDA, e é a etapa mais lenta. O tempo cresce com o número de tópicos, `FINAL_PROFESSOR_K` e `n`
- Os modelos são carregados uma vez por processo. Para várias consultas, reutilize o mesmo `Recomendador`
- A busca esparsa diferencia maiúsculas de minúsculas, então os textos indexados e os tópicos devem estar no mesmo formato
- `busca/busca_hibrida_old.py` é a versão anterior da busca e não é mais usada
