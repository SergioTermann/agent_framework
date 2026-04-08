# Agent Framework Platform
FROM python:3.10-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    FLASK_APP=agent_framework.web.web_ui

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY plugins ./plugins
COPY rust_extensions ./rust_extensions
COPY go_services ./go_services
COPY .env.example ./
COPY data ./data

RUN uv sync --no-dev

RUN mkdir -p data/knowledge data/chroma data/workflows data/conversations

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["uv", "run", "agent-framework-web"]
