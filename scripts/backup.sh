#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

echo "[BACKUP] Starting backup at $TIMESTAMP"

# Postgres dump
echo "[BACKUP] Dumping Postgres..."
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h postgres -U osint -d osint \
    --no-password \
    | gzip > "$BACKUP_DIR/postgres_${TIMESTAMP}.sql.gz"
echo "[BACKUP] Postgres done: postgres_${TIMESTAMP}.sql.gz"

# Prune old backups
echo "[BACKUP] Pruning backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "*.gz" -mtime +${RETENTION_DAYS} -delete
echo "[BACKUP] Pruning done"

echo "[BACKUP] Backup complete at $(date +%Y%m%dT%H%M%S)"
