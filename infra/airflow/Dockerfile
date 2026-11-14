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

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt
