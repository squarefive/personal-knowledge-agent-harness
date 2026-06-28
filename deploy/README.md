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
APP_IMAGE_TAG=latest docker compose -f deploy/docker-compose.yml config
```

The app container starts with `PKA_CLOUD_ONLY=true`; if `DATABASE_URL_FILE` cannot be read or resolves to an empty value, Web startup fails instead of falling back to local SQLite/Qdrant mode.

The app command initializes the PostgreSQL schema before starting the Web process:

```bash
python scripts/init-postgres-schema.py && python -m personal_knowledge_agent web --host 0.0.0.0 --port 8787 --no-open
```

## Start

From the repository root:

```bash
APP_IMAGE_TAG=latest docker compose -f deploy/docker-compose.yml pull app
APP_IMAGE_TAG=latest docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs --tail=100 app postgres nginx
```

Then open:

```text
http://124.223.210.44
```

## Backup

For this single-host Compose deployment, run PostgreSQL backups through the `postgres` container so the database can stay private inside the Compose network:

```bash
sudo scripts/backup-postgres-compose.sh --output-dir deploy/backups --keep 7
```

Automatic deployments run the backup as the SSH deployment user. Make sure that user can write `deploy/backups/`:

```bash
sudo chown -R ubuntu:ubuntu /opt/personal-knowledge-agent/deploy/backups
chmod 750 /opt/personal-knowledge-agent/deploy/backups
```

## CI/CD

Production app images are built by GitHub Actions and pushed to GitHub Container Registry:

```text
ghcr.io/squarefive/personal-knowledge-agent-harness:<commit-sha>
ghcr.io/squarefive/personal-knowledge-agent-harness:latest
```

The production Compose file pulls the app image from GHCR. It does not build the app image on the server.

The workflow runs only after pushes to `main`:

1. Run the test suite.
2. Build and push the app image with both `<commit-sha>` and `latest` tags.
3. Connect to the production server over SSH.
4. Upload the Compose and deployment scripts needed by the server.
5. Run `scripts/deploy-production.sh` with `APP_IMAGE_TAG=<commit-sha>`.

Configure these GitHub Actions repository secrets before enabling automatic deployment:

- `PROD_HOST`: production server host, for example `124.223.210.44`.
- `PROD_USER`: SSH user, for example `ubuntu`.
- `PROD_DEPLOY_DIR`: server deployment directory, for example `/opt/personal-knowledge-agent`.
- `PROD_SSH_KEY`: private SSH key used by GitHub Actions to log in to the server.

The `PROD_USER` must be able to run Docker Compose and write `deploy/backups/` in the deployment directory.

Application runtime secrets must stay on the server under `deploy/secrets/`. Do not add DeepSeek, DashScope, SMTP, PostgreSQL, or session secrets to GitHub Actions unless a future workflow explicitly needs them.

The deployment script performs a PostgreSQL backup before replacing the app container:

```bash
APP_IMAGE_TAG=<commit-sha> scripts/deploy-production.sh
```

## Rollback

To roll back the app container to a previous image tag, run from the server deployment directory:

```bash
APP_IMAGE_TAG=<previous-commit-sha> docker compose -f deploy/docker-compose.yml pull app
APP_IMAGE_TAG=<previous-commit-sha> docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml logs --tail=100 app
```
