FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app/src" \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY scripts ./scripts
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8787

CMD ["python", "-m", "personal_knowledge_agent", "web", "--host", "0.0.0.0", "--port", "8787", "--no-open"]
