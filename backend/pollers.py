"""
pollers.py — Background poll loops for OSINT Nexus.

All functions use lazy `import main as _m` inside the function body to avoid
circular imports (main.py imports from pollers.py at startup).

Functions:
    poll_flights    — FR24 ADS-B flight data → WebSocket broadcast
    poll_rss        — RSS feed ingestion
    poll_telegram   — Telegram channel scraping + video download
    poll_sitrep     — Layer 3/4: hourly SITREP generation + prediction scoring
    poll_red_alert  — OREF Red Alert civil-defense feed (Israel)
"""

import asyncio
import hashlib
import logging
import time

logger = logging.getLogger(__name__)

# Module-level constant used by poll_red_alert (safe — no main dependency)
RED_ALERT_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
_red_alert_403_last_logged: float = 0.0


async def poll_flights():
    import main as _m
    import httpx

    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        while True:
            await asyncio.sleep(30)
            _m.metrics["flight_polls"] += 1
            try:
                resp = await client.get(_m.FR24_URL)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                aircraft_list = []
                for key, val in data.items():
                    if key in ["full_count", "version", "stats"]:
                        continue
                    if not isinstance(val, list) or len(val) < 14:
                        continue
                    icao = str(val[0])
                    lat = val[1]
                    lng = val[2]
                    heading = val[3]
                    alt_ft = val[4]
                    speed_kts = val[5]
                    ac_type = str(val[8])
                    callsign = str(val[13] or val[16] or icao).strip()
                    alt_m = round(alt_ft * 0.3048)
                    speed_m = round(speed_kts * 0.51444)
                    is_mil = _m.is_military(callsign, icao) or _m.is_military(ac_type, "")
                    aircraft_list.append({
                        "id": key,
                        "callsign": callsign.upper(),
                        "country": "Unknown",
                        "lat": lat,
                        "lng": lng,
                        "alt": alt_m,
                        "speed": speed_m,
                        "heading": heading,
                        "military": is_mil,
                    })
                aircraft_list = aircraft_list[:150]
                if aircraft_list:
                    _m.last_aircraft[:] = aircraft_list
                    await _m.manager.broadcast({"type": "AIRCRAFT_UPDATE", "data": aircraft_list, "ts": time.time()})
                    _m.metrics["last_success"]["flights"] = _m.utc_now_iso()
            except Exception as e:
                _m.metrics["flight_errors"] += 1
                logger.warning(f"[FR24] Error: {e}")


async def poll_rss():
    import main as _m
    import httpx
    import feedparser
    import re

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        while True:
            _m.metrics["rss_polls"] += 1
            for feed_cfg in _m.RSS_FEEDS_EN:
                try:
                    resp = await client.get(feed_cfg["url"])
                    if resp.status_code != 200:
                        continue
                    feed_text = resp.text
                    parsed = await asyncio.to_thread(feedparser.parse, feed_text)
                    for entry in parsed.entries[:25]:
                        aid = _m.article_id(entry)
                        if not _m._track_seen_article(aid):
                            continue
                        if not _m.is_relevant(entry):
                            # Keep non-relevant article ids out of dedupe registry.
                            _m.seen_articles.discard(aid)
                            try:
                                _m._seen_articles_order.remove(aid)
                            except ValueError:
                                pass
                            continue

                        title = getattr(entry, "title", "No title")
                        summary = getattr(entry, "summary", getattr(entry, "description", ""))
                        summary = re.sub(r"<[^>]+>", "", summary)[:300]

                        geo = await _m.geolocate_event(title, summary, aid, allow_ai=False, use_geocoder=False)
                        _trust = _m.SOURCE_RELIABILITY.get(feed_cfg["source"], 65)
                        _confidence = "HIGH" if _trust >= 75 else "MEDIUM" if _trust >= 60 else "LOW"
                        event = {
                            "id": f"rss_{aid[:10]}",
                            "type": geo["type"],
                            "desc": f"[{feed_cfg['source']}] {title}",
                            "lat": geo["lat"],
                            "lng": geo["lng"],
                            "source": feed_cfg["source"],
                            "url": getattr(entry, "link", None) or getattr(entry, "id", None) or "",
                            "timestamp": _m.utc_now_iso(),
                            "insufficient_evidence": geo["insufficient_evidence"],
                            "observed_facts": geo["observed_facts"],
                            "model_inference": geo["model_inference"],
                            "confidence_score": _trust,
                            "confidence": _confidence,
                            "confidence_reason": f"{feed_cfg['source']} — source trust {_trust}/100",
                        }
                        await _m.ingest_event(event)
                        await asyncio.sleep(0.2)
                    _m.metrics["last_success"]["rss"] = _m.utc_now_iso()
                except Exception as e:
                    _m.metrics["rss_errors"] += 1
                    logger.warning(f"[RSS] Error: {e}")
            await asyncio.sleep(60)


async def poll_telegram():
    import main as _m
    import httpx

    headers = {"User-Agent": "Mozilla/5.0 (OSINT-Nexus/1.0)"}
    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
        while True:
            _m.metrics["telegram_polls"] += 1
            for cfg in _m.TELEGRAM_CHANNELS:
                try:
                    url = f"https://t.me/s/{cfg['slug']}"
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    _m.metrics["last_success"]["telegram"] = _m.utc_now_iso()
                    posts = _m.parse_telegram_posts(resp.text, cfg["slug"])
                    if not posts:
                        continue

                    candidates = posts[-max(1, _m.TELEGRAM_LOOKBACK_POSTS):]
                    pending = [p for p in candidates if f"tg_{cfg['slug']}_{p['post_id']}" not in _m.seen_telegram_posts]
                    for p in pending[-max(1, _m.TELEGRAM_MAX_NEW_PER_POLL):]:
                        pid = f"tg_{cfg['slug']}_{p['post_id']}"
                        _m._track_seen_telegram(pid)

                        text = p["text"][:500]
                        geo = await _m.geolocate_event(f"[{cfg['source']}] Telegram Update", text, pid, allow_ai=True)
                        event = {
                            "id": pid,
                            "type": geo["type"],
                            "desc": f"[{cfg['source']}] {text[:240]}",
                            "lat": geo["lat"],
                            "lng": geo["lng"],
                            "source": cfg["source"],
                            "timestamp": p["timestamp"],
                            "url": p["url"],
                            "lang": cfg["lang"],
                            "insufficient_evidence": geo["insufficient_evidence"],
                            "observed_facts": geo["observed_facts"],
                            "model_inference": geo["model_inference"],
                        }
                        if p.get("has_video"):
                            remote_video_src = str(p.get("video_src") or "").strip()
                            local_video = None
                            # Try direct CDN download first (yt-dlp telegram extractor is unreliable)
                            if remote_video_src:
                                local_video = await asyncio.to_thread(_m.download_video_direct, remote_video_src, pid)
                            # Fall back to yt-dlp if direct download failed
                            if not local_video:
                                local_video = await asyncio.to_thread(_m.download_telegram_video, p["url"], pid)
                            if local_video:
                                event["video_url"] = local_video
                            elif _m.is_playable_video_url(remote_video_src):
                                event["video_url"] = remote_video_src
                            event["has_video"] = True

                        video_meta = _m.infer_video_metadata(event.get("desc", ""), bool(event.get("has_video")), geo.get("geo_method", "fallback"))
                        event.update(video_meta)

                        await _m.ingest_event(event)

                    if len(_m.seen_telegram_posts) > 6000:
                        _m.seen_telegram_posts.clear()
                    _m.metrics["last_success"]["telegram"] = _m.utc_now_iso()
                except Exception as e:
                    _m.metrics["telegram_errors"] += 1
                    logger.warning(f"[TELEGRAM] Error {cfg['slug']}: {e}")
            await asyncio.sleep(max(1, _m.TELEGRAM_POLL_INTERVAL_SEC))


async def poll_sitrep(interval_sec: int = 3600):
    """Layer 3+4: generate SITREP every hour, score past predictions."""
    import main as _m
    import psycopg as _psycopg  # noqa: F401 — used via _m.psycopg below

    await asyncio.sleep(120)  # wait for pollers to fill data first
    while True:
        try:
            recent = _m.v2_store.fetch_recent_v2_events_pg(
                database_url=_m.DATABASE_URL,
                psycopg_mod=_m.psycopg,
                now_iso=_m.utc_now_iso,
                limit=300,
            )
            if not recent:
                recent = list(reversed(_m.events_history[-300:]))

            # Score pending predictions before generating new ones
            scored = _m.score_sitrep_predictions(recent)
            if scored:
                logger.info("[SITREP] Scored %d pending predictions", scored)

            result = await asyncio.to_thread(
                _m._reasoning_engine.generate_sitrep,
                _m._graph_store, _m.groq_client, recent,
            )

            if result.get("sitrep"):
                sitrep_id = f"sitrep_{_m.utc_now_iso()}"
                _m.persist_ai_report("sitrep", result, event_fp="")
                watch_items = result.get("watch_items") or []
                if watch_items:
                    _m.store_sitrep_watch_items(sitrep_id, watch_items)
                logger.info(
                    "[SITREP] Generated: quality=%s cluster=%d contradictions=%d watches=%d",
                    result.get("data_quality"), result.get("dominant_cluster_size", 0),
                    len(result.get("contradictions") or []), len(watch_items),
                )
        except Exception as exc:
            logger.error("[SITREP] poll_sitrep failed: %s", exc)
        await asyncio.sleep(interval_sec)


async def poll_red_alert():
    import main as _m
    import httpx

    global _red_alert_403_last_logged

    headers = {
        "Referer": "https://www.oref.org.il/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
    }
    async with httpx.AsyncClient(timeout=5, headers=headers) as client:
        while True:
            await asyncio.sleep(3)
            _m.metrics["red_alert_polls"] += 1
            try:
                resp = await client.get(RED_ALERT_URL)
                if resp.status_code != 200:
                    _m.metrics["red_alert_errors"] += 1
                    if resp.status_code == 403:
                        # Geo-blocking: server reachable, IP not Israeli.
                        # Mark as healthy poll so watchdog doesn't false-alarm.
                        _m.metrics["last_success"]["red_alert"] = _m.utc_now_iso()
                        _now = asyncio.get_event_loop().time()
                        if _now - _red_alert_403_last_logged > 600:
                            logger.warning("[RED ALERT] 403 Forbidden — OREF geo-blocking this IP (logged once per 10m)")
                            _red_alert_403_last_logged = _now
                    continue
                # Healthy poll — mark success regardless of whether an alert is active.
                # Empty/null response = no active sirens = still working correctly.
                _m.metrics["last_success"]["red_alert"] = _m.utc_now_iso()
                if not resp.text.strip():
                    continue
                try:
                    data = resp.json()
                except Exception:
                    continue
                if not data:
                    continue

                alert_id = data.get("id", "")
                if not _m._track_seen_alert(alert_id):
                    continue

                alert_title = data.get("title", "Red Alert")
                cities = data.get("data", [])
                ts_now = _m.utc_now_iso()

                for city in cities:
                    lat, lng = _m.geolocate_alert(city)
                    eid = hashlib.sha256(f"{alert_id}_{city}".encode()).hexdigest()[:10]
                    event = {
                        "id": f"alert_{eid}",
                        "type": "STRIKE",
                        "desc": f"[Red Alert] {alert_title}: {city}",
                        "lat": lat,
                        "lng": lng,
                        "source": "Red Alert",
                        "timestamp": ts_now,
                        "insufficient_evidence": False,
                        "observed_facts": ["Official civil-defense alert feed"],
                        "model_inference": [],
                    }
                    await _m.ingest_event(event)
            except Exception as e:
                _m.metrics["red_alert_errors"] += 1
                logger.warning(f"[RED ALERT] Error: {e}")
