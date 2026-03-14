#!/usr/bin/env python3
"""
migrate_data.py — One-shot SQLite → PostgreSQL data migration.

Usage:
    cd backend && python scripts/migrate_data.py

Reads from the SQLite file at OSINT_DB_PATH (or /tmp/osint_nexus.db) and
copies every row into the PostgreSQL database configured via DATABASE_URL /
POSTGRES_* environment variables.

Safe to re-run: uses INSERT ... ON CONFLICT DO NOTHING so already-migrated
rows are skipped.  Tables that are already fully populated in Postgres are
skipped entirely for performance.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

# ── make sure we can import from backend/ whether run as a script or module ──
_HERE = Path(__file__).resolve().parent          # backend/scripts/
_BACKEND = _HERE.parent                          # backend/
sys.path.insert(0, str(_BACKEND))

from config import DATABASE_URL, DB_PATH         # noqa: E402
import psycopg                                   # noqa: E402
from psycopg.rows import dict_row                # noqa: E402
import db_postgres                               # noqa: E402


# ── tables in migration order (respect FK dependencies) ────────────────────
# Each entry: (sqlite_table, pg_table, conflict_column)
# conflict_column is used for ON CONFLICT DO NOTHING.
TABLES: list[tuple[str, str, str]] = [
    ("users",               "users",               "username"),
    ("revoked_tokens",      "revoked_tokens",      "sig"),
    ("events",              "events",              "id"),
    ("reviews",             "reviews",             "id"),
    ("saved_views",         "saved_views",         "id"),
    ("watchlists",          "watchlists",          "id"),
    ("pinned_incidents",    "pinned_incidents",    "incident_id"),
    ("handoff_notes",       "handoff_notes",       "id"),
    ("notification_rules",  "notification_rules",  "id"),
    ("media_analysis",      "media_analysis",      "event_id"),
    ("eval_samples",        "eval_samples",        "id"),
    ("audit_logs",          "audit_logs",          "id"),
    ("user_mfa_totp",       "user_mfa_totp",       "username"),
    ("totp_used_codes",     "totp_used_codes",     "username"),  # composite PK
    ("user_passkeys",       "user_passkeys",       "credential_id"),
]

# Tables whose PK is a serial (Postgres auto-increment); we skip the id column
# on INSERT so Postgres assigns its own sequence value.
SERIAL_PK_TABLES = {
    "reviews", "saved_views", "watchlists", "handoff_notes",
    "notification_rules", "eval_samples", "audit_logs", "user_passkeys",
}


def _pg_count(pg_cur, table: str) -> int:
    pg_cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
    return int(pg_cur.fetchone()["c"])


def _sqlite_count(sq_cur, table: str) -> int:
    try:
        sq_cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
        return int(sq_cur.fetchone()["c"])
    except sqlite3.OperationalError:
        return -1  # table doesn't exist in this SQLite DB


def migrate_table(sq_conn, pg_conn, sqlite_table: str, pg_table: str, conflict_col: str) -> int:
    """Copy all rows from sqlite_table to pg_table. Returns number of rows inserted."""
    sq_cur = sq_conn.cursor()
    sq_cur.row_factory = sqlite3.Row

    row_count = _sqlite_count(sq_cur, sqlite_table)
    if row_count == -1:
        print(f"  SKIP  {sqlite_table}: table not found in SQLite")
        return 0
    if row_count == 0:
        print(f"  SKIP  {sqlite_table}: empty in SQLite")
        return 0

    with pg_conn.cursor() as pg_cur:
        pg_existing = _pg_count(pg_cur, pg_table)

    if pg_existing >= row_count:
        print(f"  SKIP  {pg_table}: Postgres already has {pg_existing} rows (SQLite has {row_count})")
        return 0

    # Fetch all rows from SQLite
    sq_cur.execute(f"SELECT * FROM {sqlite_table}")
    rows = sq_cur.fetchall()
    if not rows:
        return 0

    inserted = 0
    with pg_conn.cursor() as pg_cur:
        for row in rows:
            d = dict(row)

            # For serial-PK tables, drop 'id' so Postgres auto-assigns it.
            # We use credential_id / username / etc. as conflict target instead.
            if pg_table in SERIAL_PK_TABLES and "id" in d:
                d.pop("id")

            cols = list(d.keys())
            vals = list(d.values())
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)

            # Build conflict clause
            if pg_table == "totp_used_codes":
                conflict_clause = "ON CONFLICT (username, code) DO NOTHING"
            else:
                conflict_clause = f"ON CONFLICT ({conflict_col}) DO NOTHING"

            sql = (
                f"INSERT INTO {pg_table} ({col_names}) "
                f"VALUES ({placeholders}) "
                f"{conflict_clause}"
            )
            try:
                pg_cur.execute(sql, vals)
                inserted += pg_cur.rowcount
            except Exception as exc:
                print(f"    WARN  row skipped in {pg_table}: {exc}")

    pg_conn.commit()
    return inserted


def main() -> None:
    sqlite_path = DB_PATH
    if not Path(sqlite_path).exists():
        print(f"SQLite file not found at {sqlite_path} — nothing to migrate.")
        sys.exit(0)

    if not DATABASE_URL:
        print("DATABASE_URL is not set — cannot connect to PostgreSQL.")
        sys.exit(1)

    print(f"Source SQLite : {sqlite_path}")
    print(f"Target Postgres: {DATABASE_URL.split('@')[-1]}")  # hide credentials
    print()

    sq_conn = sqlite3.connect(sqlite_path)
    sq_conn.row_factory = sqlite3.Row

    pg_conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    # Ensure schema exists before we copy data
    db_postgres.init_pg_schema(pg_conn)

    total_inserted = 0
    for sqlite_table, pg_table, conflict_col in TABLES:
        print(f"  Migrating {sqlite_table} → {pg_table} …", end=" ")
        n = migrate_table(sq_conn, pg_conn, sqlite_table, pg_table, conflict_col)
        if n > 0:
            print(f"{n} rows inserted")
        total_inserted += n

    sq_conn.close()
    pg_conn.close()

    print()
    print(f"Migration complete. Total rows inserted: {total_inserted}")


if __name__ == "__main__":
    main()
