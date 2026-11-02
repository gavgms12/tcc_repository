FROM apache/airflow:3.0.6

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends git chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Commit fixo (origin/main) para build reprodutível; scriptLattes não tem releases
# versionadas, então pinamos no mesmo commit usado no ambiente local.
RUN git clone https://github.com/jpmenachalco/scriptLattes.git /opt/scriptLattes \
    && cd /opt/scriptLattes \
    && git checkout fb713a1b77eb954910cee48bd275e714267f61cd \
    && python3 -m venv venv \
    && venv/bin/pip install --no-cache-dir --upgrade pip \
    && venv/bin/pip install --no-cache-dir -r requirements.txt \
    && rm -f chromedriver \
    && ln -s /usr/bin/chromedriver chromedriver \
    && chown -R airflow:root /opt/scriptLattes

USER airflow

COPY requirements.txt requirements-busca.txt /tmp/

RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Dependências da busca (opcionais: INSTALL_BUSCA=false gera uma imagem menor).
# torch só CPU: a versão padrão do PyPI traz CUDA e deixa a imagem vários GB maior
ARG INSTALL_BUSCA=true
RUN if [ "$INSTALL_BUSCA" = "true" ]; then \
        pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
        && pip install --no-cache-dir -r /tmp/requirements-busca.txt; \
    fi
