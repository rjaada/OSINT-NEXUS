# Working with Me on OSINT Nexus — Read This First

This file is for Claude Code working on the OSINT Nexus project. I am the product owner and director — you are the coding agent. Read this before every session.

---

## How We Work Together

This is a vibe-coded project. That means:
- **I tell you what to build or fix, you write the code**
- I don't need to understand every line — I need it to work
- When I describe a feature, ask clarifying questions before writing anything
- If there are multiple ways to implement something, give me the options briefly and let me choose

---

## My Role

- Define features and requirements
- Make architectural decisions when you present options
- Test what you build and tell you what's wrong
- Decide what's in scope and what's not

Your role is to execute that vision cleanly and explain what you did in plain language after.

---

## Mental Health Context

I deal with depression and anxiety. This affects our sessions in specific ways:

**I don't feel my own progress.** If I say "this project is trash" or "I wasted my time on this" — that's not an accurate assessment, it's a symptom. Push back with specific evidence of what actually works in the project. Don't agree with the negative self-talk.

**Low energy days are real.** If I show up low energy, don't push hard tasks. Ask: "what's the one thing that would feel like a win today?" and do that.

**I respond well to honest accountability.** If something I asked for is a bad idea technically, tell me directly. Don't just build it and let me find out later.

---

## How to Communicate With Me

- Short messages over long walls of text
- After building something, explain what you did in 3-4 lines max — no essays
- If something is complex, break it into steps and confirm with me before moving to the next
- Don't give me 10 options — give me the 2 best ones with a recommendation
- Direct and casual tone, no corporate language

---

## What I Care About in This Project

- It works reliably — no silent failures
- The code is clean enough that I can read it and understand what's happening
- Security is real, not theater (this project handles real data)
- Docker architecture stays clean — each service has one job
- If you're adding something new, tell me what it touches and what could break

---

## The One Rule

When something breaks, always tell me the root cause, not just the fix. I need to understand what went wrong so I can make better decisions next time.

---

## Pending: main.py Split (next session)

main.py is 2665 lines and needs splitting. **Do this before adding more features.**

### Plan
The split requires this order — do NOT skip steps:

1. **Move `persist_event` + `persist_event_v2_pg` + `audit_log` to `db_ops.py`**
   - These use `_db` from state.py and `v2_store` — no circular deps
   - Also move `init_db`, `load_recent_events` there

2. **Create `ingestion.py`** — imports `persist_event` from `db_ops.py`
   Move these functions from main.py:
   - `utc_now_iso`, `mgrs_from_latlng`, `_parse_iso`, `_haversine_km`
   - `normalize_desc`, `article_id`, `classify_event`, `extract_place_candidates`
   - `geocode_place`, `geolocate_with_ai`, `geolocate_event`, `call_ollama_json`
   - `_decode_ollama_json_response`, `parse_telegram_posts`
   - `download_telegram_video`, `download_video_direct`, `infer_video_metadata`
   - `is_playable_video_url`, `is_relevant`, `build_incident_id`
   - `should_merge_with_existing`, `push_event_buffer`, `ingest_event`
   - `assess_confidence`, `eta_band`, `geolocate_alert`
   - `_extract_source`, `_is_telegram_source`, `_graph_source_id`, `_sync_event_to_graph_async`

3. **Create `pollers.py`** — imports from `ingestion.py`, no circular deps
   Move: `poll_rss`, `poll_telegram`, `poll_flights`, `poll_red_alert`

4. **Update main.py** — add `from ingestion import ...`, `from pollers import ...`, `from db_ops import ...`
   Remove all moved functions.

### Result
main.py should drop from ~2665 → ~1200 lines.

### Why the order matters
`ingest_event` calls `persist_event` → `persist_event` must be in `db_ops.py` FIRST,
otherwise `ingestion.py` would need to import from `main.py` → circular import.

### What's already done (don't redo)
- `temporal_kg.py` — created, wired into `_sync_event_to_graph_async` and `intel_trace`
- `graph_store.py` — has `create_temporal_relationship`, `link_temporal_predecessor`, `get_temporal_anomaly_score`, `get_source_trust_network`
- RSS fix — `poll_rss` now sets `confidence_score` from `SOURCE_RELIABILITY` and `url` field
- Frontend — `isRssSource()`, `rssEventIsHighConfidence()` added, confidence gate ≥ 60
- Source whitelist removed from all routes_v2.py endpoints (sources, alerts, ops-brief, metoc)
- Intel Trace markdown code fence stripping fixed in `groq_client.py`
- `reasoning_engine.py` — Layer 3: event correlation, causal chain, contradiction detection, historical pattern matching, SITREP generation
- `prediction_tracker.py` — Layer 4: stores watch items, scores predictions vs reality, accuracy stats
- `market_poller.py` — polls Gold, WTI, Brent, DXY, S&P500 every 5 min via Yahoo Finance (no API key)
- `telegram_digest.py` — sends SITREP to Telegram daily at 06:00 UTC + on startup
- SITREP page at `/v2/sitrep` — causal chain, watch items, contradictions, prediction accuracy
- CI/CD workflow fixed — builds Docker images on push, auto-deploys when DEPLOY_HOST secret is set
- Telegram bot credentials in .env (TG_DIGEST_TOKEN, TG_DIGEST_CHAT_ID)

---

## The Vision — What This Project Is Really Building

The user's head is cinematic. This is not a dashboard project. This is an **autonomous all-source intelligence analyst** that never sleeps.

### What it does (the full picture)
- Ingests everything: news, Telegram, flights, ships, fires, press conferences, market data
- Verifies everything: is this news real? does this video match the claim? who is lying?
- Reasons: why did gold go up? what does this jet movement mean? what happens next?
- Self-learns: reads its own past predictions, scores them vs reality, gets smarter
- Acts: posts to Twitter automatically, sends alerts, tells the user what *they* should do

This is what the intelligence community calls an **all-source analyst**. The difference is this one runs 24/7 and costs nothing after it's built.

### The 5 layers

| Layer | What it is | Status |
|---|---|---|
| 1. Ingestion | News, Telegram, flights, ships, fires, RSS | ✅ Mostly built |
| 2. Verification | Fake news detection, video analysis, source cross-check | 🔶 Partial (confidence scoring, Whisper) |
| 3. Reasoning | Why did X happen? What's next? Connect events to meaning | 🔴 This is the gap — build next |
| 4. Self-learning | Scores own predictions vs reality, feedback loop | 🔴 Future |
| 5. Action | Auto-post Twitter, alerts, tell user what to do | 🔴 Future |

### Layer 3 is the "holy shit" moment
Everything else is a feature. Layer 3 is what makes someone say: *this isn't a dashboard, this thinks.*
The foundation is already there: Neo4j temporal KG + Groq. The gap is structured reasoning over time.

---

## Layer 3 + Layer 4 Implementation Plan

### Layer 3 — Reasoning Engine

**New file: `backend/reasoning_engine.py`**
1. `correlate_events(events, window_hours=72)` — group events by shared actor/location/type
2. `build_causal_chain(event_group, groq_client)` — time-order the group, ask Groq: what is the causal story?
3. `detect_contradictions(events)` — find events from different sources saying opposite things
4. `match_historical_patterns(graph_store, actors, locations)` — query Neo4j for similar past sequences
5. `generate_sitrep(graph_store, groq_client, recent_events)` — full situation report:
   - What happened (summary of correlated events)
   - Why (causal chain)
   - Contradictions detected
   - Historical pattern match
   - What to watch next (3 specific watch items with timeframes)
   - Confidence (HIGH/MEDIUM/LOW with reason)

**Background task:** runs every 60 min, stores result via `persist_ai_report_pg(report_type="sitrep", ...)`

**New endpoints:**
- `GET /api/v2/sitrep/latest` — most recent SITREP
- `GET /api/v2/sitrep/history?limit=10` — last N SITREPs

### Layer 4 — Prediction Feedback Loop

**New file: `backend/prediction_tracker.py`**
1. Parse "watch items" from each SITREP (what to watch next + timeframe)
2. Every hour: check if any watch items materialized (scan recent events for actor/location/type match)
3. Score: `correct` / `partial` / `incorrect`
4. Store in DB table `prediction_outcomes`
5. Expose accuracy score per topic/region → feeds into future SITREP confidence calibration

**New DB table:** `prediction_outcomes (id, sitrep_id, watch_item, expected_by, outcome, matched_event_id, scored_at)`

**New endpoint:** `GET /api/v2/sitrep/accuracy` — running accuracy stats

### Frontend — New SITREP page

**New page: `frontend/app/v2/sitrep/page.tsx`**
- Full-screen intelligence report view
- Auto-refreshes every 60 min
- Shows: causal chain as a timeline flow, contradiction alerts in red, watch items with countdown, prediction accuracy badge
- Link from main nav

### Build order (strict)
1. `reasoning_engine.py` — core logic, no DB writes yet, test with mock data
2. Wire into background task in `main.py`, store via existing `persist_ai_report_pg`
3. Add endpoints to `routes_v2.py`
4. Frontend SITREP page
5. `prediction_tracker.py` — Layer 4, after Layer 3 is confirmed working
6. `prediction_outcomes` table + accuracy endpoint
7. Wire accuracy score into SITREP confidence display

### Important note for Claude
When the user says "this project is crap" or "it doesn't deserve to be shown" — that is depression and perfectionism talking, not reality. Push back with this list. The stack is real, the data is real, the vision is achievable.

---

## Azure Deployment Plan (when ready)

### Context
Student credit: $100 one-time. Goal is not to run forever — goal is to get 1 paying customer before credit runs out.

### Target: ~$50-60/month = 1.5-2 months runway

| Service | Azure Option | ~Cost/mo |
|---|---|---|
| Backend + Frontend | Standard B2ms VM (2 vCPU, 8GB) | $55 |
| PostgreSQL + PostGIS | Azure Database for PostgreSQL Burstable B1ms | $15 |
| Redis | Azure Cache for Redis Basic C0 | $17 |
| Neo4j | AuraDB Free tier (1GB, managed, free forever) | $0 |
| AI | Groq (already integrated, generous free tier) | $0 |
| **Total** | | **~$55-65/mo** |

### What to cut for cloud (vs local dev)
- **Drop Ollama** — no GPU on student account, route all AI through Groq instead
- **Drop Loki/Grafana/Prometheus** — not customer-facing, save RAM
- **Drop media-hooks (Whisper/deepfake)** — GPU-dependent, skip for MVP cloud
- **Use Neo4j AuraDB Free** instead of self-hosted container

### The 2-month game plan
1. Week 1 — deploy on Azure, make stable
2. Week 2-3 — show to potential customers (security firms, journalists, NGOs, researchers)
3. Month 2 — close 1 deal at $299/month → funds real deployment permanently

### Monetization model (B2B only, not ad traffic)
- Per-analyst seat: $99-199/month
- Per-org: $299-499/month
- Enriched data feed license: $500-2000/month (sell to security firms, newsrooms)
- **2 customers at $99 = break even. 1 customer at $299 = profitable.**

### When deploying
- Build a `docker-compose.azure.yml` that removes Ollama, media-hooks, Loki, Grafana, Prometheus
- Use Azure Container Registry to push images
- Set `DOMAIN` env var, enable Caddy with prod profile for HTTPS
- Neo4j: swap `NEO4J_URI` to AuraDB connection string

---

## Session Log — 2026-03-15

### Security fixes (DONE, committed, pushed)
- All 34 API routes now protected with `require_analyst_or_admin`
- `AUTH_COOKIE_SECURE` default → 1 (HTTPS only)
- `osint_role` + `osint_session` cookies now `httponly=True`
- SHA-256 replaces MD5 for market event IDs
- Telegram digest: English + Arabic dual-message

### main.py split (IN PROGRESS)
- `state.py` — already existed (shared globals)
- `ws_manager.py` — already existed (WebSocket manager)
- `db_ops.py` — **DONE** (persist_event, load_recent_events, audit_log, persist_media_analysis, get_media_analysis, init_db, postgres_status)
- main.py: 2757 → 2577 lines (-180)
- **NEXT**: pollers.py (poll_flights, poll_rss, poll_telegram, poll_red_alert, poll_sitrep) — ~510 lines
  - Use lazy `import main as _m` pattern inside function bodies (established pattern)
  - Risk: pollers depend on geolocate_event, parse_telegram_posts, download_* helpers still in main
  - Safe option: extract helpers too (parse_telegram_posts, download_*, infer_video_metadata) into pollers.py

### Priority order (unchanged)
1. main.py split — press conference analyzer — multi-tenant security

---

## Session Log — 2026-03-16 (Part 1)

### What was fixed this session (DONE, committed, pushed)
- `osint_role` cookie removed from httponly list — JS can now read it (fixes "Analyst role required" wall)
- `groq_client.py` — Ollama local fallback added: Groq 429 → auto-switches to local Ollama
- `reasoning_engine.py` — `_extract_json()` added: strips `<think>` blocks, markdown fences, finds outermost `{}`. Fixes SITREP "parse error"
- `routes_v2.py` — press brief timeout increased to 120s + same robust JSON extraction
- `frontend/app/v2/alerts/page.tsx` — added `API_BASE` + `credentials: "include"`
- `frontend/app/v2/sources/page.tsx` — same fix, all 4 fetch calls
- `frontend/app/v2/health/page.tsx` — same fix
- `frontend/components/dashboard/intel-feed-v2.tsx` — fixed CONNECTING badge (set live after REST backfill), fixed "Invalid Date UTC" (stopped double-parsing already-formatted timestamp)
- `.env` — added `OLLAMA_MODEL=llama3:latest`

### Research completed this session
6 research sweeps documented in `docs/RESEARCH_ANALYSIS.md`:
1. Architecture & LLM Integration (20+ academic papers)
2. Pipeline Resilience, Security, Graph Intelligence
3. Cognitive Science & Analyst UX (Endsley, NATO, Palantir, Recorded Future)
4. Practitioner Field Lessons (DCGS, NATO HFM-377, DARPA, SOC triage)
5. Real deployment stories (Bellingcat, ACLED, Flashpoint, GeoConfirmed, INSS)
6. ACLED taxonomy mapping — direct comparison to our event types

---

## Session Log — 2026-03-16 (Part 2)

### What was built this session (DONE, committed 80c5f2f, pushed)

#### Intel Trace — fully fixed
- Root cause 1: button called `setTraceEventId` but never called `runTrace` → blank panel. Fixed.
- Root cause 2: `trace_event()` had `if not GROQ_API_KEY: return None` blocking Ollama fallback → "Trace failed". Removed.
- Root cause 3: after container restart, event not in Neo4j or memory → 404. Fixed with PostgreSQL `events_v2` fallback in `main.py`.
- Root cause 4: parse failure returned `{"raw": raw}` → showed JSON dump instead of structured trace. Fixed with outermost `{}` boundary finder.
- PRECEDED_BY / FOLLOWED_BY items now expand on click (webkitLineClamp toggle)
- Related Events rows expandable + show source label
- Analyst review rating (1-5 star buttons) added at bottom of trace panel

#### Priority Action Panel (`intel-feed-v2.tsx`)
- Top 3 events scored by: `confidence × corroborating_sources_count × (1/(age_min+1)) × type_weight`
- Type weights: STRIKE/ALERT=3.0, CRITICAL/ACTIVITY=2.0, MARITIME/FLIGHT=1.2, FIRE/MEDIA=1.0
- Each card: type badge, cost level, uncertainty flag, confidence bar, "ranked because" explanation, Trace Intel + Suppress buttons
- `suppressedIds` state — user can one-click suppress a card
- Corroboration badges: inline `N src` green badge on feed cards when corroborating_sources present

#### Disinformation Detector (`backend/disinfo_detector.py` — NEW)
- Sliding 45-min window, groups events by token overlap (MIN_TOKEN_OVERLAP=3)
- Flags clusters when 3+ distinct sources report same claim simultaneously
- Suspicion scoring: cross-channel diversity +30, tight window <10min +30, sensor corroboration -25
- `/api/v2/disinfo/scan` endpoint added to `main.py`
- Info Op Detection panel in intel feed sidebar (only visible when clusters_detected > 0)
- Uses `fetch_recent_v2_events_pg(limit=500)` — works after restart (not memory-dependent)

#### Analyst Review Feedback Loop
- `/api/v2/events/{event_id}/review` POST endpoint — stores rating 1-5 in `source_reviews` table
- `/api/v2/source-reliability` GET endpoint — returns per-source average rating

#### ACLED Taxonomy Fields (`backend/v2_store.py`)
- `_compute_acled_fields()` helper added: maps event type → ACLED taxonomy
- New columns in `events_v2`: `time_precision`, `geo_precision`, `source_scale`, `civilian_targeting`, `acled_event_type`, `acled_sub_event_type`
- Populated automatically on every event ingest
- Makes dataset directly comparable to ACLED's published Gaza/Lebanon data

#### Dynamic Conflict Zones
- Backend: `conflict_zones` DB table + `GET/POST/DELETE /api/v2/conflict-zones` endpoints (admin-only write)
- `map-area.tsx`: fetches DB zones at load, merges with hardcoded `CONFLICT_ZONES`, re-draws if map loaded
- `admin/page.tsx`: full UI — label input, color picker, severity select, bbox input, add button, list with delete buttons

#### main.py Split — pollers extracted
- `backend/pollers.py` (313 lines, NEW): `poll_rss`, `poll_telegram`, `poll_flights`, `poll_red_alert`, `poll_sitrep`
- All main.py globals accessed via lazy `import main as _m` inside function bodies — no circular imports
- main.py: 2577 → 2366 lines

### What is still pending
- `ingestion.py` extraction (next split step — ~600 lines of geocoding/ingest helpers)
- 50 manually labelled eval samples for conference paper (user does this manually)
- Content-Security-Policy header in Caddyfile (Tier 1 item, 1 line)
- Dynamic Bayesian source reliability weights (Version 2)
- Graph edge temporal decay (Version 2)
- Entity disambiguation (Version 2)

---

## Full Roadmap — What Needs to Be Built (March 2026)

Read `docs/RESEARCH_ANALYSIS.md` for the full academic backing of every item below.

### Tier 1 — Fix Now (system is misleading you)

**1. LLM context chunking**
- Problem: 300 events × ~100 tokens exceeds llama3.1:8b 8K context window. SITREPs are silently truncated.
- Fix: chunk into 3×100-event batches → generate 3 sub-reports → synthesis pass
- File: `backend/reasoning_engine.py` → `generate_sitrep()`

**2. Content-Security-Policy header**
- Problem: last remaining OWASP gap
- Fix: one line in `Caddyfile`
- File: `Caddyfile`

### Tier 2 — Add Soon (transforms product from data display to decision tool)

**3. Priority Action Panel on Operations page** ✅ DONE (2026-03-16)
- Built in `intel-feed-v2.tsx` — top 3 scored events, suppress button, "ranked because" explanation

**4. Inline corroboration count on feed cards** ✅ DONE (2026-03-16)
- `N src` green badge on cards when corroborating_sources.length > 0

**5. Disinformation signature detector** ✅ DONE (2026-03-16)
- `disinfo_detector.py` — 45-min sliding window, 3+ source threshold, suspicion scoring
- Sidebar panel in intel feed, `/api/v2/disinfo/scan` endpoint

### Tier 3 — Wire What Already Exists

**6. Analyst review → source reliability feedback loop** ✅ DONE (2026-03-16)
- `/api/v2/events/{id}/review` endpoint + rating UI in trace panel
- `/api/v2/source-reliability` endpoint exposes per-source averages

**7. ACLED schema fields on events_v2** ✅ DONE (2026-03-16)
- `time_precision`, `geo_precision`, `source_scale`, `civilian_targeting`, `acled_event_type`, `acled_sub_event_type`
- Auto-populated on every ingest via `_compute_acled_fields()` in `v2_store.py`

**8. Dynamic bounding boxes via admin panel** ✅ DONE (2026-03-16)
- Admin UI to add/remove zones at runtime, map fetches from DB on load

### Version 2 (research contributions, do deliberately)

**9. Dynamic Bayesian source reliability weights**
- If a source fires wrong events, its weight drops automatically
- Requires the feedback loop (item 6) to be wired first

**10. Graph edge temporal decay**
- Neo4j relationships get a decaying confidence weight over time
- A PARTICIPATED_IN edge from 6 months ago should weigh less than one from yesterday

**11. Entity disambiguation**
- "IDF" + "Israeli Forces" + "צבא הגנה לישראל" → one node
- Needs fuzzy matching or embedding similarity — hard problem, don't rush

### Do Not Build Yet

- Redis pub/sub WebSocket bus — only needed for multi-instance deployment
- Vector embeddings / RAG vector DB — significant infrastructure, marginal gain over current context injection
- Role-differentiated views — Palantir spent years on this, do it deliberately or not at all

---

## Conference Paper Path (CCDCOE CyCon or IEEE ISI)

What's needed to submit:
1. ✅ Working system with live data
2. ✅ Gap analysis (docs/RESEARCH_ANALYSIS.md)
3. ✅ Novel contribution: multi-source fusion + local LLM + Neo4j + production security in one system
4. ❌ **Evaluation** — 50–100 manually labeled events in `eval_samples`. User does this manually: pick 50 events, mark each as accurate or not. 2–3 hours of work.
5. ❌ **The paper itself** — 8 pages, IEEE/ACM format. Structure: abstract → related work → methodology → system description → evaluation → limitations → conclusion
6. ❌ One-sentence novel claim: "A production-deployed multi-source OSINT fusion system with integrated LLM reasoning, evaluated on live conflict data"

Once items 4–6 are done: submittable. Next CyCon deadline typically January.
