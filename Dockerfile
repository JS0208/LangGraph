# syntax=docker/dockerfile:1.7
# Multi-stage build for the GraphRAG FastAPI backend.
# Sprint 0 skeleton — keeps fallback-first behavior even when external services are absent.

ARG PYTHON_VERSION=3.13-slim

FROM python:${PYTHON_VERSION} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

FROM base AS deps
COPY requirements.txt ./
RUN pip install -r requirements.txt

FROM deps AS runtime
COPY app ./app
COPY tests ./tests
COPY scripts ./scripts

ENV HOST=0.0.0.0 \
    PORT=8000 \
    MAX_TURNS=3

EXPOSE 8000

# Healthcheck: 라우터의 OpenAPI 페이지를 호출 (FastAPI 기본)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/docs').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
