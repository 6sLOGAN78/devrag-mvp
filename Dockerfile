# syntax=docker/dockerfile:1
# One app image: SPA (built), Go API binary, Python API, Nginx, under tini (D-23, D-24, D-26).
# Python 3.13 deviates from docs/18-deployment/docker.md ("3.10 slim"), see D-16.

FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM golang:1.25-alpine AS go-build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
COPY conf/embed.go conf/schema.json ./conf/
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/ragflow_server ./cmd

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    PATH=/ragflow/.venv/bin:$PATH \
    PYTHONPATH=/ragflow \
    SERVICE_CONF=/ragflow/conf/service_conf.yaml
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx tini curl util-linux \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*
WORKDIR /ragflow
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.9.18 \
    && uv sync --frozen --no-dev --no-install-project \
    && pip uninstall -y uv \
    && rm -rf /root/.cache
COPY api ./api
COPY common ./common
COPY conf ./conf
COPY scripts/render_conf.py ./scripts/render_conf.py
COPY --from=go-build /out/ragflow_server /ragflow/bin/ragflow_server
COPY --from=web-build /web/dist /ragflow/web/dist
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/proxy.conf /etc/nginx/proxy.conf
COPY docker/nginx/ragflow.conf /etc/nginx/conf.d/ragflow.conf
COPY docker/nginx/ragflow.https.conf /etc/nginx/ragflow.https.conf
COPY docker/entrypoint.sh docker/entrypoint_init.sh docker/healthcheck.sh docker/prepare_runtime.sh /ragflow/docker/
RUN chmod 0755 /ragflow/docker/*.sh /ragflow/bin/ragflow_server \
    && mkdir -p /ragflow/logs /ragflow/conf
EXPOSE 80 443
ENTRYPOINT ["tini", "--", "/ragflow/docker/entrypoint.sh"]
