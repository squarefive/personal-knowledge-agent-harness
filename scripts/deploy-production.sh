#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

: "${APP_IMAGE_TAG:=latest}"

scripts/backup-postgres-compose.sh --output-dir deploy/backups --keep 7
APP_IMAGE_TAG="$APP_IMAGE_TAG" docker compose -f deploy/docker-compose.yml pull app
APP_IMAGE_TAG="$APP_IMAGE_TAG" docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs --tail=100 app
