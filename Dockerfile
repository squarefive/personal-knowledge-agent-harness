FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app/src" \
    PIP_INDEX_URL="https://mirrors.cloud.tencent.com/pypi/simple" \
    PIP_DEFAULT_TIMEOUT=120 \
    PATH="/usr/local/bin:$PATH"

WORKDIR /app

COPY deploy/requirements.txt ./deploy/requirements.txt
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r deploy/requirements.txt

COPY README.md ./
COPY scripts ./scripts
COPY src ./src

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8787

CMD ["python", "-m", "personal_knowledge_agent", "web", "--host", "0.0.0.0", "--port", "8787", "--no-open"]
