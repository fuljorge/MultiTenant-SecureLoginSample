# syntax=docker/dockerfile:1.10
# Control Plane (FastAPI) e worker (specs/001-identity-access, T073).
# Contexto de build: raiz do repositório (workspace uv).
#   docker build -f services/control-plane/Dockerfile -t cap-control-plane .
# API:     a imagem padrão (uvicorn na porta 8000)
# Worker:  docker run ... cap-control-plane cap-worker
# Migrações: docker run ... cap-control-plane alembic upgrade head

FROM ghcr.io/astral-sh/uv:0.11.22@sha256:16b63af0e7342dd372da9ca989ea9fa542fc68f4640972d59a8450a5240fe42e AS uv

FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependências primeiro (camada reaproveitada enquanto o lock não muda).
COPY pyproject.toml uv.lock ./
COPY services/control-plane/pyproject.toml services/control-plane/
RUN uv sync --locked --no-dev --package cap-control-plane --no-install-workspace
COPY services/control-plane/ services/control-plane/
RUN uv sync --locked --no-dev --package cap-control-plane --no-editable

FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
# Correções de segurança do Debian publicadas depois da imagem base (varredura Trivy).
RUN apt-get update && apt-get upgrade -y --no-install-recommends     && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 cap \
    && useradd --system --uid 10001 --gid cap --no-create-home cap
WORKDIR /app/services/control-plane
COPY --from=build --chown=root:root /app/.venv /app/.venv
COPY --from=build --chown=root:root /app/services/control-plane/alembic.ini ./
COPY --from=build --chown=root:root /app/services/control-plane/migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "cap_control_plane.main:run", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
