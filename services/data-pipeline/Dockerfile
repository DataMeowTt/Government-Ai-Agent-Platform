# syntax=docker/dockerfile:1.7
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10 \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip \
    && python -m pip install --retries 10 --timeout 180 pyspark==4.1.1

COPY pyproject.toml ./
COPY . .

RUN python -m pip install --retries 10 --timeout 180 -e .

CMD ["python", "-m", "jobs.plan_snapshot", "--help"]
