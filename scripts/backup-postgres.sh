#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --output-dir DIR [--keep N]" >&2
}

output_dir=""
keep="7"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-dir)
      if [ "$#" -lt 2 ]; then
        usage
        exit 2
      fi
      output_dir="$2"
      shift 2
      ;;
    --keep)
      if [ "$#" -lt 2 ]; then
        usage
        exit 2
      fi
      keep="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [ -z "$output_dir" ]; then
  usage
  exit 2
fi

case "$keep" in
  ''|*[!0-9]*|0)
    echo "--keep must be a positive integer" >&2
    exit 2
    ;;
esac

if [ -n "${DATABASE_URL_FILE:-}" ]; then
  if [ ! -f "$DATABASE_URL_FILE" ]; then
    echo "DATABASE_URL_FILE does not exist: $DATABASE_URL_FILE" >&2
    exit 2
  fi
  database_url="$(tr -d '\r\n' < "$DATABASE_URL_FILE")"
else
  database_url="${DATABASE_URL:-}"
fi

if [ -z "$database_url" ]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "pg_dump is required" >&2
  exit 2
fi

mkdir -p "$output_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="$output_dir/postgres-$timestamp.sql.gz"
backup_tmp="$backup_file.tmp"

cleanup_tmp() {
  rm -f -- "$backup_tmp"
}

trap cleanup_tmp EXIT
pg_dump "$database_url" | gzip -c > "$backup_tmp"
mv -- "$backup_tmp" "$backup_file"
trap - EXIT

find "$output_dir" -maxdepth 1 -type f -name 'postgres-*.sql.gz' \
  | sort -r \
  | awk -v keep="$keep" 'NR > keep' \
  | while IFS= read -r old_backup; do
      rm -- "$old_backup"
    done

echo "$backup_file"
