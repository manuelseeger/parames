FROM ghcr.io/astral-sh/uv:debian-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/
COPY config/ config/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["parames"]
