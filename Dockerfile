FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/
COPY config/ config/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["parames"]
