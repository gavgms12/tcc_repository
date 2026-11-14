# Arquitetura da infraestrutura

Como os serviços do projeto se encaixam, por que foram configurados assim e como operá-los.

## Serviços

```
                    rede Docker "tcc_default" (criada pelo compose)
┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│  postgres ◄──── airflow-init (db migrate, roda uma vez e termina)         │
│     ▲                                                                     │
│     │ metadados                                                           │
│  airflow-apiserver ◄── execution API ── airflow-scheduler (roda as tasks) │
│     ▲                                    │        ▲                       │
│     │                                    │        │ parse                 │
│     │                     airflow-dag-processor ──┘                       │
│     │                                    │                                │
│     │                                    ▼ S3 (usuário de serviço)        │
│     │              minio-init ──────► minio (bronze · silver · gold)      │
│     │              (buckets + usuário, roda uma vez)                      │
└─────┼────────────────────────────────────┼────────────────────────────────┘
      │ 127.0.0.1:8085                     │ 127.0.0.1:9010 (S3) · 9011 (console)
   navegador                         scripts no host
```

| Serviço | Imagem | Papel |
|---------|--------|-------|
| `minio` | `bitnamilegacy/minio:2025.7.23-debian-12-r5` | Data lake S3, um bucket por camada |
| `minio-init` | mesma do MinIO (usa o `mc` dela) | Cria buckets e o usuário de serviço; idempotente |
| `postgres` | `postgres:16-alpine` | Metadados do Airflow (execuções, estado dos assets) |
| `airflow-init` | `tcc-airflow` (local) | `airflow db migrate` |
| `airflow-apiserver` | `tcc-airflow` | Interface web, REST API e Execution API |
| `airflow-scheduler` | `tcc-airflow` | Agenda e executa as tasks (LocalExecutor) |
| `airflow-dag-processor` | `tcc-airflow` | Faz o parse das DAGs |

Ordem de subida, garantida por `depends_on` com condição: `minio` saudável → `minio-init` concluído → `postgres` saudável → `airflow-init` concluído → serviços do Airflow.

## Decisões

**Compose único, com `name: tcc`.** Um arquivo só é mais simples de ler que vários. O nome fixo do projeto isola containers, rede e volumes (`tcc_*`) de outros projetos na mesma máquina; antes o nome vinha da pasta e colidia com outro checkout de mesmo nome. Os serviços se encontram pelo nome (`minio`, `postgres`), sem `container_name` nem aliases manuais.

**Postgres para o Airflow.** O modo `standalone` guardava os metadados em SQLite dentro do container, então cada recriação apagava o histórico, o estado dos assets (que encadeiam Bronze → Silver → Gold) e a senha do admin. Com Postgres em volume, isso persiste.

**Componentes do Airflow separados.** É o desenho do compose oficial do Airflow 3: cada componente tem seu healthcheck e pode ser reiniciado sozinho. Todos usam a âncora `x-airflow-common`, então a configuração é escrita uma vez. Não há `triggerer` porque nenhuma task é *deferrable*.

**Menor privilégio no MinIO.** O pipeline usa o usuário de serviço `MINIO_ACCESS_KEY`, criado pelo `minio-init` com a política `pipeline-rw` (acesso só aos três buckets). O root (`MINIO_ROOT_USER`) só é usado pelo console e pelo init.

**Privilégios do scriptLattes só onde precisa.** O Chromium do scriptLattes precisa de `SYS_ADMIN` para o sandbox. Com LocalExecutor as tasks rodam no `airflow-scheduler`, então só ele recebe essa capability e o cache montado (`data/cache`).

**Código na imagem e montado em desenvolvimento.** A imagem contém `src/` e funciona sozinha; o compose monta `./src` e `./dags` somente leitura por cima, então edições valem sem rebuild. Antes o repositório inteiro (com `.env`, `.git` e os arquivos internos do MinIO) era montado com escrita.

**Portas só em `127.0.0.1`.** Nada fica exposto na rede local.

**Segredos só no `.env`.** O compose recusa subir (`${VAR:?}`) se faltar algum. A senha do admin do Airflow vem de `AIRFLOW_ADMIN_PASSWORD`, em vez de ser gerada a cada subida.

## Imagem do MinIO

As imagens oficiais `minio/minio` deixaram de ser distribuídas publicamente em 2025 (o Docker Hub e o quay.io negam o download). A `bitnamilegacy/minio` ainda pode ser baixada e tem versão fixa, mas **não recebe atualizações de segurança**. Para um ambiente local, com portas restritas a esta máquina, o risco é aceitável. Para produção, as alternativas são:

- compilar o MinIO a partir do código-fonte numa imagem própria;
- trocar por outro servidor compatível com S3 (SeaweedFS, Garage). O código só fala S3 via `boto3`, então a troca é de configuração.

## Operação

| Tarefa | Comando |
|--------|---------|
| Subir / atualizar após mudar o Dockerfile | `docker compose up -d --build` |
| Estado e saúde dos serviços | `docker compose ps` |
| Logs de um serviço | `docker compose logs -f airflow-scheduler` |
| Parar sem perder dados | `docker compose down` |
| Disparar o pipeline pela CLI | `docker compose exec airflow-scheduler airflow dags trigger bronze_scrape_professores_sigaa` |
| Cliente do MinIO | `docker compose exec minio mc ls` (configure antes com `mc alias set`) |
| **Apagar tudo, inclusive dados** | `docker compose down -v` ⚠️ |

### Trocar segredos

- **Senha do admin do Airflow:** edite `AIRFLOW_ADMIN_PASSWORD` e rode `docker compose up -d`.
- **Senha do usuário de serviço do MinIO:** edite `MINIO_SECRET_KEY` e rode `docker compose up -d`. O `minio-init` atualiza o usuário.
- **`MINIO_ROOT_PASSWORD`:** é lida só quando o volume é criado pela primeira vez. Para trocá-la depois, use `mc admin` ou recrie o volume.
- **`POSTGRES_PASSWORD`:** também é fixada na criação do volume. Para trocá-la, use `ALTER USER` no banco.
- **`AIRFLOW_FERNET_KEY`:** criptografa as conexões salvas no banco. Não troque sem rotacionar ([documentação](https://airflow.apache.org/docs/apache-airflow/stable/security/secrets/fernet.html)).
