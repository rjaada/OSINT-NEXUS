# OSINT Nexus — Operations Runbook

> Last updated: 2026-03-14

---

## Deploy (First Time)

```bash
git clone https://github.com/rjaada/OSINT-NEXUS.git
cd OSINT-NEXUS
cp .env.example .env
# Fill in .env with your values
docker compose build
docker compose up -d
```

## Deploy (Upgrade)

```bash
git pull origin main
docker compose build backend
docker compose up -d backend
```

## Roll Back a Bad Deploy

```bash
git log --oneline -10          # find the last good commit
git checkout <commit-hash>
docker compose build backend
docker compose up -d backend
```

---

## Health Checks

### Check overall health
```bash
curl http://localhost:8000/api/health
```
Returns `{"status":"ok"}` or `{"status":"degraded","checks":{...}}` with which dependency failed.

### Check ops metrics
```bash
curl http://localhost:8000/api/ops/health
```

---

## Troubleshooting

### Postgres is down
1. `docker compose ps postgres` — check if container is running
2. `docker compose logs postgres --tail=50` — look for errors
3. `docker compose restart postgres` — attempt restart
4. Check disk space: `df -h`

### Neo4j auth failure
The Neo4j graph store is non-critical. The system operates without it.
To reset Neo4j password:
```bash
docker compose exec neo4j cypher-shell -u neo4j -p <current-password> \
  "ALTER CURRENT USER SET PASSWORD FROM '<old>' TO '<new>';"
```
Update NEO4J_PASSWORD in .env to match, then restart backend.

### Ollama not responding
```bash
docker compose logs ollama --tail=30
docker compose restart ollama
```
Models are cached in `ollama_data/` volume — no re-download needed.

### Red Alert always shows 403
Expected — OREF geo-blocks non-Israeli IPs. Not a bug. Safe to ignore.

### No events showing on frontend
1. Check `/api/health` — is Postgres connected?
2. Check `/api/ops/health` — are pollers running?
3. Check backend logs: `docker compose logs backend --tail=100`

---

## Backups

### Manual backup (Postgres)
```bash
docker compose --profile prod run --rm backup /backup.sh
```

### Restore from backup
```bash
# Find the backup file
ls -la /var/lib/docker/volumes/osint_backup_data/_data/

# Restore
gunzip -c postgres_20260314_120000.sql.gz | \
  docker compose exec -T postgres psql -U osint -d osint
```

---

## User Management

### Add a new user
POST /api/auth/register with admin credentials.

### Reset a password
```bash
# Via break-glass code in .env (AUTH_BREAK_GLASS_CODE)
POST /api/auth/login with break-glass credentials
```

---

## DEFCON Levels

| Level | Meaning |
|-------|---------|
| 5 | Baseline monitoring |
| 4 | Elevated activity |
| 3 | High tempo, multiple theaters |
| 2 | Critical events, corroborated |
| 1 | Imminent/active escalation |

Check current level: `GET /api/v2/system`

---

## Data Source Terms

| Source | Terms | Commercial? |
|--------|-------|-------------|
| adsb.lol | Personal/research use | Contact for commercial |
| AISStream | Free tier available | Paid tiers exist |
| NASA FIRMS | Public domain | Free |
| OREF Red Alert | Public | Free |
| Telegram (public channels) | Public data | Check channel ToS |

---

## Emergency Contacts

- Repo: https://github.com/rjaada/OSINT-NEXUS
- Issues: https://github.com/rjaada/OSINT-NEXUS/issues
