FROM node:22-slim AS frontend
WORKDIR /build
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci
COPY webapp/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:debian-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --locked

COPY src/ src/
COPY config/ config/
COPY --from=frontend /build/dist/ webapp/dist/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["parames"]
