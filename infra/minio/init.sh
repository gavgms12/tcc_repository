#!/bin/bash
# Roda uma vez a cada `docker compose up` (serviço minio-init) e é idempotente:
#   1. cria os buckets das camadas;
#   2. cria o usuário de serviço do pipeline com acesso só a esses buckets.
# O usuário root do MinIO fica restrito à administração (console, este script).
set -euo pipefail

# A imagem da Bitnami reinicia o servidor após a configuração inicial, então o
# primeiro healthcheck verde pode chegar antes de a porta ficar estável.
for tentativa in $(seq 1 30); do
    if mc alias set local "http://minio:9000" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; then
        break
    fi
    if [ "$tentativa" -eq 30 ]; then
        echo "MinIO não respondeu após 60s." >&2
        exit 1
    fi
    sleep 2
done

BUCKETS=("$MINIO_BRONZE_BUCKET" "$MINIO_SILVER_BUCKET" "$MINIO_GOLD_BUCKET")
for bucket in "${BUCKETS[@]}"; do
    mc mb --ignore-existing "local/$bucket"
done

recursos=""
for bucket in "${BUCKETS[@]}"; do
    recursos+="\"arn:aws:s3:::$bucket\",\"arn:aws:s3:::$bucket/*\","
done

politica=/tmp/pipeline-policy.json
cat > "$politica" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:*"],
      "Resource": [${recursos%,}]
    }
  ]
}
EOF

mc admin policy create local pipeline-rw "$politica" >/dev/null
# `user add` com a mesma chave atualiza a senha; seguro rodar de novo.
mc admin user add local "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null
mc admin policy attach local pipeline-rw --user "$MINIO_ACCESS_KEY" >/dev/null 2>&1 || true

echo "MinIO pronto: buckets ${BUCKETS[*]} e usuário de serviço '$MINIO_ACCESS_KEY' (política pipeline-rw)."
