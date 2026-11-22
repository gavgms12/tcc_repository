# Imagem do Airflow com o código do pipeline e o scriptLattes.
# Build: docker compose build (contexto = raiz do repositório).
ARG AIRFLOW_VERSION=3.0.6
ARG PYTHON_VERSION=3.12
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

# ARGs declarados antes do FROM precisam ser repetidos para valer aqui dentro.
ARG AIRFLOW_VERSION

USER root

# Chromium + chromedriver para o Selenium do scriptLattes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Commit fixo para build reprodutível; o scriptLattes não tem releases versionadas.
RUN git clone https://github.com/jpmenachalco/scriptLattes.git /opt/scriptLattes \
    && cd /opt/scriptLattes \
    && git checkout fb713a1b77eb954910cee48bd275e714267f61cd \
    && python3 -m venv venv \
    && venv/bin/pip install --no-cache-dir --upgrade pip \
    && venv/bin/pip install --no-cache-dir -r requirements.txt \
    && rm -f chromedriver \
    && ln -s /usr/bin/chromedriver chromedriver \
    && chown -R airflow:root /opt/scriptLattes

# Cache dos modelos do Hugging Face (BGE-M3, ~2 GB). Volume no compose; o
# diretório existe na imagem para o volume herdar dono e permissões.
RUN mkdir -p /opt/huggingface && chown airflow:root /opt/huggingface && chmod 775 /opt/huggingface

USER airflow

# Reinstalar apache-airflow na mesma versão impede que as dependências do
# projeto atualizem/rebaixem o Airflow (recomendação da documentação oficial).
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt

# Indexação no Qdrant (BGE-M3). As dependências vêm do requirements-busca.txt
# da recuperação; sem ele (ou com INSTALL_BUSCA=false) a imagem fica só com o
# pipeline de dados. O colchete em "tx[t]" faz o COPY não falhar se o arquivo
# não existir. torch só CPU: a versão padrão do PyPI traz CUDA (vários GB a mais).
ARG INSTALL_BUSCA=true
COPY requirements.txt requirements-busca.tx[t] /tmp/
RUN if [ "$INSTALL_BUSCA" = "true" ] && [ -f /tmp/requirements-busca.txt ]; then \
        pip install --no-cache-dir "torch>=2.4,<3" --index-url https://download.pytorch.org/whl/cpu \
        && pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements-busca.txt; \
    else \
        echo "Imagem sem as dependências da busca (requirements-busca.txt ausente ou INSTALL_BUSCA=false)."; \
    fi

# O código vai para a imagem (ela funciona sozinha); em desenvolvimento o
# docker-compose monta ./src por cima, então edições valem sem rebuild.
COPY --chown=airflow:root src/ /opt/project/src/

# src/ tem os pacotes do pipeline; /opt/project recebe a recuperacao/ montada
# pelo compose (mantida na raiz do repositório).
ENV PYTHONPATH=/opt/project/src:/opt/project \
    SCRIPTLATTES_DIR=/opt/scriptLattes \
    SCRIPTLATTES_CACHE_DIR=/opt/project/data/cache/scriptlattes \
    HF_HOME=/opt/huggingface
