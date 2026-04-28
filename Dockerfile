FROM ghcr.io/astral-sh/uv:debian-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --locked

COPY src/ src/
COPY config/ config/
COPY webapp/ webapp/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["parames"]
