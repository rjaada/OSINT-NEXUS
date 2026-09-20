#!/bin/sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"
umask 077

LOCK_DIR="$BACKUP_DIR/.backup.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[BACKUP] Backup already in progress" >&2
    exit 1
fi

echo "[BACKUP] Starting backup at $TIMESTAMP"

# Postgres dump. Avoid a pipeline: POSIX sh has no pipefail, so pg_dump and
# compression must each succeed before the backup is published atomically.
FINAL_BACKUP="$BACKUP_DIR/postgres_${TIMESTAMP}.sql.gz"
DUMP_TMP="$BACKUP_DIR/.postgres_${TIMESTAMP}_$$.sql.tmp"
GZIP_TMP="$BACKUP_DIR/.postgres_${TIMESTAMP}_$$.sql.gz.tmp"
cleanup() {
    rm -f "$DUMP_TMP" "$GZIP_TMP"
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup 0
trap 'cleanup; exit 1' HUP INT TERM

echo "[BACKUP] Dumping Postgres..."
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h postgres -U osint -d osint \
    --no-password > "$DUMP_TMP"
gzip -c "$DUMP_TMP" > "$GZIP_TMP"
mv "$GZIP_TMP" "$FINAL_BACKUP"
rm -f "$DUMP_TMP"
echo "[BACKUP] Postgres done: postgres_${TIMESTAMP}.sql.gz"

# Prune old backups
echo "[BACKUP] Pruning backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "*.gz" -mtime +${RETENTION_DAYS} -delete
echo "[BACKUP] Pruning done"

echo "[BACKUP] Backup complete at $(date +%Y%m%dT%H%M%S)"
