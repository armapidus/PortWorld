ARG PORTWORLD_NODE_IMAGE=node:22-bookworm-slim

FROM ${PORTWORLD_NODE_IMAGE} AS node-runtime

FROM python:3.11-slim AS python-builder

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/

WORKDIR /src/backend

COPY backend/ ./

RUN uv build --wheel . --out-dir /tmp/dist

FROM python:3.11-slim AS python-installer

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/
COPY --from=python-builder /tmp/dist/*.whl /tmp/dist/

RUN uv pip install --system /tmp/dist/*.whl \
    && rm -rf /tmp/dist /root/.cache/uv /bin/uv /bin/uvx

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=node-runtime /usr/local/ /usr/local/
COPY --from=python-installer /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/

# Keep the runtime rooted at /app so BACKEND_DATA_DIR=backend/var resolves
# consistently for both local Compose and later container-hosted installs.
RUN mkdir -p /app/backend/var

EXPOSE 8080

CMD ["python", "-m", "backend.cli", "serve"]
