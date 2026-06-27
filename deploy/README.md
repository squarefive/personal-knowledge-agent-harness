# Single-host Docker Compose Deployment

This directory is a single-server cloud deployment baseline for the Web app, PostgreSQL with pgvector, and an HTTP nginx reverse proxy.

HTTP on port 80 is temporary. Do not treat this as the long-term public production boundary; add HTTPS termination before long-term external use.

## Server-only secrets

Create secret files on the server under `deploy/secrets/`, owned by root and readable only by root:

```bash
sudo install -d -m 700 -o root -g root deploy/secrets
sudo install -m 600 -o root -g root /dev/null deploy/secrets/database_url
sudo install -m 600 -o root -g root /dev/null deploy/secrets/postgres_password
sudo install -m 600 -o root -g root /dev/null deploy/secrets/deepseek_api_key
sudo install -m 600 -o root -g root /dev/null deploy/secrets/smtp_password
sudo install -m 600 -o root -g root /dev/null deploy/secrets/session_secret
sudo install -m 600 -o root -g root /dev/null deploy/secrets/dashscope_api_key
```

Do not commit real secret files. `deploy/.gitignore` ignores `secrets/`, backups, local env files, and override compose files.

The app service runs as root inside the container so Docker Compose file-backed secrets can remain root-only on the host and readable at runtime. The database still has no public port; only nginx exposes HTTP port 80.

Expected secret contents:

- `database_url`: PostgreSQL URL for the internal Compose database, for example `postgresql://pka:<password>@postgres:5432/pka`.
- `postgres_password`: password used by the `postgres` container.
- `deepseek_api_key`: DeepSeek API key.
- `smtp_password`: QQ SMTP authorization code, not the QQ account password.
- `session_secret`: random high-entropy value for signing application sessions.
- `dashscope_api_key`: optional Qwen/DashScope embedding API key; leave this file empty if semantic embeddings should stay disabled.

Set non-secret mail identity values in the server environment before running Compose:

```bash
export ALLOWED_LOGIN_EMAILS="1033795760@qq.com"
export SMTP_USER="1033795760@qq.com"
export MAIL_FROM="1033795760@qq.com"
```

Make sure the password embedded in `database_url` is the same value written to `postgres_password`.

## Local validation

From the repository root:

```bash
sudo docker compose -f deploy/docker-compose.yml config
```

The app container starts with `PKA_CLOUD_ONLY=true`; if `DATABASE_URL_FILE` cannot be read or resolves to an empty value, Web startup fails instead of falling back to local SQLite/Qdrant mode.

The app command initializes the PostgreSQL schema before starting the Web process:

```bash
python scripts/init-postgres-schema.py && python -m personal_knowledge_agent web --host 0.0.0.0 --port 8787 --no-open
```

## Start

From the repository root:

```bash
sudo docker compose -f deploy/docker-compose.yml up -d --build
sudo docker compose -f deploy/docker-compose.yml ps
sudo docker compose -f deploy/docker-compose.yml logs --tail=100 app postgres nginx
```

Then open:

```text
http://124.223.210.44
```

## Backup

Run PostgreSQL backups from a host or maintenance container that has `pg_dump`:

```bash
DATABASE_URL_FILE=deploy/secrets/database_url scripts/backup-postgres.sh --output-dir deploy/backups --keep 7
```
