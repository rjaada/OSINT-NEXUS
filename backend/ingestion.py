# ingestion.py — geocoding, classification, and event ingest helpers

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

import intel_utils as iutils
from db_ops import utc_now_iso, persist_event

logger = logging.getLogger("osint")
graph_logger = logging.getLogger("osint.graph")

try:
    import mgrs as _mgrs_lib  # type: ignore
except Exception:
    _mgrs_lib = None


# ---------------------------------------------------------------------------
# Thin wrappers — call iutils directly (no circular _m dependency)
# ---------------------------------------------------------------------------

def mgrs_from_latlng(lat: float, lng: float) -> Optional[str]:
    if _mgrs_lib is None:
        return None
    try:
        converter = _mgrs_lib.MGRS()
        return str(converter.toMGRS(lat, lng))
    except Exception:
        return None


def _parse_iso(ts: str):
    return iutils.parse_iso(ts, now_iso=utc_now_iso)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return iutils.haversine_km(lat1, lon1, lat2, lon2)


def normalize_desc(desc: str) -> str:
    return iutils.normalize_desc(desc)


def article_id(entry) -> str:
    return iutils.article_id(entry)


def classify_event(title: str, summary: str) -> str:
    import main as _m
    return iutils.classify_event(title, summary, _m.EVENT_TYPE_KEYWORDS_AR)


def extract_place_candidates(text: str) -> List[str]:
    import main as _m
    return iutils.extract_place_candidates(text, _m.PLACE_COORDS)


def assess_confidence(event: dict, nearby: list, age_min: float) -> Tuple[int, str, List[str]]:
    import main as _m
    return iutils.assess_confidence(event, nearby, age_min, _m.SOURCE_RELIABILITY)


def eta_band(event: dict) -> str:
    return iutils.eta_band(event)


def geolocate_alert(city: str) -> tuple:
    import main as _m
    return iutils.geolocate_alert(city, _m.ISRAEL_CITY_COORDS)


def _extract_source(event: dict) -> str:
    return iutils.extract_source(event)


def _is_telegram_source(event: dict) -> bool:
    import main as _m
    return iutils.is_telegram_source(event, _m.TELEGRAM_SOURCE_SET)


# ---------------------------------------------------------------------------
# Real implementations
# ---------------------------------------------------------------------------

def _graph_source_id(source: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", source.lower()).strip("_")
    if not normalized:
        normalized = "unknown"
    return f"source:{normalized}"


async def _sync_event_to_graph_async(event: dict) -> None:
    import main as _m
    if _m._graph_store is None or not _m._graph_store.status().get("connected"):
        return
    try:
        payload = dict(event)
        payload["source_name"] = _extract_source(event)
        payload["source"] = payload["source_name"]
        await asyncio.to_thread(_m._graph_store.upsert_event_node, payload)

        # Entity extraction via Groq — Telegram + high-trust RSS sources (trust >= 0.80)
        # High-trust RSS: BBC News, DW News, France 24, NPR
        _HIGH_TRUST_RSS = {"BBC News", "DW News", "France 24", "NPR"}
        src_name = payload["source_name"]
        _run_extraction = _is_telegram_source(event) or src_name in _HIGH_TRUST_RSS
        if _m.groq_client.groq_available() and _run_extraction:
            desc = str(event.get("description") or event.get("desc") or event.get("title") or "")
            if desc:
                event_id = str(event.get("id") or "")
                entities = await asyncio.to_thread(_m.groq_client.extract_entities, desc)
                if entities.get("actors"):
                    await asyncio.to_thread(_m._graph_store.link_event_actors, event_id, entities["actors"])
                if entities.get("weapons"):
                    await asyncio.to_thread(_m._graph_store.link_event_weapons, event_id, entities["weapons"])

        # Temporal enrichment — predecessor linking + anomaly scoring
        import temporal_kg
        event_id = str(event.get("id") or "")
        ts = str(event.get("timestamp") or "")
        lat = event.get("lat")
        lng = event.get("lng")
        if event_id and ts and lat is not None and lng is not None:
            await asyncio.to_thread(
                temporal_kg.enrich_event_with_temporal_context,
                _m._graph_store, event_id, ts, float(lat), float(lng),
            )
    except Exception as exc:
        graph_logger.warning("[GRAPH] failed to sync event %s: %s", str(event.get("id", "")), exc)


async def geocode_place(place: str) -> Optional[Tuple[float, float]]:
    import main as _m
    if place in _m.geocode_cache:
        return _m.geocode_cache[place]
    try:
        params = {"q": place, "format": "json", "limit": 1}
        client = _m._get_geocode_client()
        r = await client.get(_m.GEOCODE_URL, params=params)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None
        lat = float(data[0]["lat"])
        lng = float(data[0]["lon"])
        _m.geocode_cache[place] = (lat, lng)
        return lat, lng
    except Exception:
        return None


def _decode_ollama_json_response(raw: str) -> Optional[dict]:
    raw_text = str(raw or "{}").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()
    try:
        parsed = json.loads(raw_text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


async def call_ollama_json(prompt: str, retries: int = 2) -> Optional[dict]:
    import main as _m
    model_chain = [_m.OLLAMA_MODEL]
    if _m.OLLAMA_FALLBACK_MODEL and _m.OLLAMA_FALLBACK_MODEL not in model_chain:
        model_chain.append(_m.OLLAMA_FALLBACK_MODEL)
    if _m._ollama_available_models:
        model_chain = [m for m in model_chain if m in _m._ollama_available_models]
    if not model_chain:
        return None
    for model_name in model_chain:
        for attempt in range(retries + 1):
            try:
                client = _m._get_ollama_client()
                resp = await client.post(
                    _m.OLLAMA_URL,
                    json={
                        "model": model_name,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1},
                    },
                    timeout=45,
                )
                resp.raise_for_status()
                raw = str(resp.json().get("response", "{}")).strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    raw = raw.replace("json", "", 1).strip()
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except httpx.HTTPStatusError as e:
                if getattr(e.response, "status_code", None) == 404:
                    _m._ollama_available_models.discard(model_name)
                    logger.warning(f"[OLLAMA] Missing model '{model_name}', removed from runtime chain")
                    break
                if attempt == retries:
                    logger.warning(f"[OLLAMA] JSON call failed ({model_name}): {e}")
                await asyncio.sleep(0.35 * (attempt + 1))
            except Exception as e:
                if attempt == retries:
                    logger.warning(f"[OLLAMA] JSON call failed ({model_name}): {e}")
                await asyncio.sleep(0.35 * (attempt + 1))
    return None


async def geolocate_with_ai(title: str, summary: str) -> Optional[dict]:
    prompt = f"""You are a geolocation extraction engine.
Return ONLY strict JSON with keys:
lat (number), lng (number), severity_1_to_10 (integer), event_type (STRIKE|MOVEMENT|CLASH|NOTAM|CRITICAL),
insufficient_evidence (boolean), observed_facts (array of short strings), model_inference (array of short strings).

Title: {title}
Summary: {summary}
"""
    result = await call_ollama_json(prompt, retries=2)
    if not result:
        return None
    try:
        lat = float(result.get("lat", 0.0))
        lng = float(result.get("lng", 0.0))
        severity = int(result.get("severity_1_to_10", 3))
        event_type = str(result.get("event_type", "CLASH")).upper()
        insufficient = bool(result.get("insufficient_evidence", False))
        observed = result.get("observed_facts") if isinstance(result.get("observed_facts"), list) else []
        inferred = result.get("model_inference") if isinstance(result.get("model_inference"), list) else []
        if event_type not in {"STRIKE", "MOVEMENT", "CLASH", "NOTAM", "CRITICAL"}:
            event_type = "CLASH"
        if abs(lat) > 90 or abs(lng) > 180:
            return None
        return {
            "lat": lat,
            "lng": lng,
            "severity": max(1, min(10, severity)),
            "type": event_type,
            "insufficient_evidence": insufficient,
            "observed_facts": [str(x)[:120] for x in observed[:4]],
            "model_inference": [str(x)[:120] for x in inferred[:4]],
        }
    except Exception:
        return None


async def geolocate_event(title: str, summary: str, fallback_seed: str, allow_ai: bool = True, use_geocoder: bool = True) -> dict:
    """Geolocation chain: place dictionary -> geocoder -> AI -> deterministic fallback."""
    import main as _m
    observed: List[str] = []
    inferred: List[str] = []

    combined = f"{title} {summary}"
    candidates = extract_place_candidates(combined)
    for place in candidates:
        if place in _m.PLACE_COORDS:
            lat, lng = _m.PLACE_COORDS[place]
            observed.append(f"Matched place mention: {place}")
            return {
                "lat": lat,
                "lng": lng,
                "type": classify_event(title, summary),
                "severity": 5,
                "observed_facts": observed,
                "model_inference": ["Location estimated from explicit place-name match."],
                "insufficient_evidence": False,
                "geo_method": "place-dict",
            }

    for place in (candidates[:2] if use_geocoder else []):
        geo = await geocode_place(place)
        if geo:
            observed.append(f"Geocoded place mention: {place}")
            return {
                "lat": geo[0],
                "lng": geo[1],
                "type": classify_event(title, summary),
                "severity": 4,
                "observed_facts": observed,
                "model_inference": ["Location estimated via geocoder for named place."],
                "insufficient_evidence": False,
                "geo_method": "geocoder",
            }

    if allow_ai:
        ai = await geolocate_with_ai(title, summary)
        if ai and not ai.get("insufficient_evidence"):
            return {
                "lat": ai["lat"],
                "lng": ai["lng"],
                "type": "CRITICAL" if ai["severity"] >= 8 else ai["type"],
                "severity": ai["severity"],
                "observed_facts": ai.get("observed_facts", []),
                "model_inference": ai.get("model_inference", []),
                "insufficient_evidence": False,
                "geo_method": "ollama",
            }

    lat = 31.5 + (hash(fallback_seed) % 14) * 0.22
    lng = 34.8 + (hash(fallback_seed[::-1]) % 14) * 0.22
    inferred.append("Insufficient location evidence; fallback coordinate used.")
    return {
        "lat": lat,
        "lng": lng,
        "type": classify_event(title, summary),
        "severity": 3,
        "observed_facts": observed,
        "model_inference": inferred,
        "insufficient_evidence": True,
        "geo_method": "fallback",
    }


def parse_telegram_posts(html_text: str, channel_slug: str) -> list:
    soup = BeautifulSoup(html_text, "html.parser")
    posts = []
    for message in soup.select("div.tgme_widget_message"):
        data_post = message.get("data-post", "")
        if not data_post.startswith(f"{channel_slug}/"):
            continue

        post_id = data_post.split("/")[-1]
        text_node = message.select_one("div.tgme_widget_message_text")
        text = text_node.get_text(" ", strip=True) if text_node else ""
        video_node = (
            message.select_one("video.tgme_widget_message_video")
            or message.select_one("video.js-message_video")
            or message.select_one("video")
        )
        video_src = None
        if video_node:
            # Telegram lazy-loads via data-src; fall back to <source> children
            video_src = (
                video_node.get("src")
                or video_node.get("data-src")
                or (video_node.select_one("source") and video_node.select_one("source").get("src"))
                or None
            )
            # Strip empty strings
            if video_src and not video_src.strip():
                video_src = None
        has_video = bool(video_node or message.select_one(".tgme_widget_message_video_player") or message.select_one(".tgme_widget_message_video_wrap"))
        if len(text) < 15 and not has_video:
            continue

        date_node = message.select_one("a.tgme_widget_message_date")
        url = date_node.get("href", f"https://t.me/{data_post}") if date_node else f"https://t.me/{data_post}"
        time_node = message.select_one("time")
        ts = time_node.get("datetime") if time_node else utc_now_iso()

        posts.append({
            "post_id": post_id,
            "text": text,
            "url": url,
            "timestamp": ts,
            "has_video": has_video,
            "video_src": video_src,
        })

    def post_sort_key(item: dict) -> int:
        try:
            return int(item["post_id"])
        except Exception:
            return 0

    posts.sort(key=post_sort_key)
    return posts


def download_telegram_video(post_url: str, event_id: str) -> Optional[str]:
    import main as _m
    if not _m.DOWNLOAD_TELEGRAM_MEDIA:
        return None
    try:
        out_tpl = str(_m.TELEGRAM_MEDIA_DIR / f"{event_id}.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--socket-timeout", "15",
            "--retries", "2",
            "--max-filesize", f"{_m.TELEGRAM_MAX_MEDIA_MB}M",
            "--restrict-filenames",
            "-f", "mp4/best[ext=mp4]/best",
            "-o", out_tpl,
            post_url,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        for ext in ("mp4", "webm", "mkv", "mov"):
            candidate = _m.TELEGRAM_MEDIA_DIR / f"{event_id}.{ext}"
            if candidate.exists():
                size_mb = candidate.stat().st_size / (1024 * 1024)
                if size_mb > _m.TELEGRAM_MAX_MEDIA_MB:
                    candidate.unlink(missing_ok=True)
                    return None
                return f"/media/telegram/{candidate.name}"
    except Exception:
        return None
    return None


def download_video_direct(cdn_url: str, event_id: str) -> Optional[str]:
    """Download a Telegram CDN video URL directly with httpx, bypassing yt-dlp."""
    import main as _m
    if not cdn_url or not _m.DOWNLOAD_TELEGRAM_MEDIA:
        return None
    try:
        import httpx as _httpx
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://t.me/"}
        max_bytes = _m.TELEGRAM_MAX_MEDIA_MB * 1024 * 1024
        with _httpx.stream("GET", cdn_url, headers=headers, follow_redirects=True, timeout=30) as r:
            if r.status_code != 200:
                return None
            ct = r.headers.get("content-type", "")
            if "video" not in ct and "octet" not in ct:
                return None
            ext = "mp4"
            if "webm" in ct:
                ext = "webm"
            dest = _m.TELEGRAM_MEDIA_DIR / f"{event_id}.{ext}"
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        dest.unlink(missing_ok=True)
                        return None
                    f.write(chunk)
        return f"/media/telegram/{dest.name}"
    except Exception:
        return None


def infer_video_metadata(desc: str, has_video: bool, geo_method: str) -> dict:
    if not has_video:
        return {}

    clues = []
    lower = (desc or "").lower()
    for place in extract_place_candidates(lower):
        clues.append(f"place_mention:{place}")

    if geo_method in {"place-dict", "geocoder"} and clues:
        tag = "LIKELY_RELATED"
        confidence = "MEDIUM"
    elif geo_method == "ollama" and clues:
        tag = "LIKELY_RELATED"
        confidence = "HIGH"
    elif clues:
        tag = "UNVERIFIED_VISUAL"
        confidence = "LOW"
    else:
        tag = "MISMATCH"
        confidence = "LOW"

    return {
        "video_assessment": tag,
        "video_confidence": confidence,
        "video_clues": clues[:4],
    }


def is_playable_video_url(url: str) -> bool:
    import main as _m
    if not url:
        return False
    if url.startswith("/media/telegram/"):
        local_path = _m.TELEGRAM_MEDIA_DIR / Path(url).name
        return local_path.exists() and local_path.is_file()
    lower = url.lower()
    # Accept direct CDN URLs from Telegram even without file extension
    if "cdn.telegram.org" in lower or "cdn1.telegram.org" in lower or "cdn2.telegram.org" in lower:
        return True
    return bool(re.search(r"\.(mp4|webm|mov|m4v)(\?|$)", lower))


def is_relevant(entry) -> bool:
    import main as _m
    text = (
        getattr(entry, "title", "") + " " +
        getattr(entry, "summary", "") + " " +
        getattr(entry, "description", "")
    ).lower()
    return any(kw in text for kw in _m.CONFLICT_KEYWORDS)


def build_incident_id(event: dict) -> str:
    text = normalize_desc(event.get("desc", ""))
    tokens = " ".join(text.split()[:10])
    lat_b = round(float(event.get("lat", 0.0)), 1)
    lng_b = round(float(event.get("lng", 0.0)), 1)
    typ = str(event.get("type", "CLASH"))
    key = f"{typ}|{lat_b}|{lng_b}|{tokens}"
    return "inc_" + hashlib.sha256(key.encode()).hexdigest()[:14]


def should_merge_with_existing(event: dict) -> Optional[str]:
    import main as _m
    now_ts = _parse_iso(str(event.get("timestamp", utc_now_iso())))
    new_norm = normalize_desc(event.get("desc", ""))
    for incident_id, existing in list(_m.incident_index.items()):
        if existing.get("type") != event.get("type"):
            continue
        old_ts = _parse_iso(str(existing.get("timestamp", utc_now_iso())))
        if abs((now_ts - old_ts).total_seconds()) > 12 * 60:
            continue
        if _haversine_km(float(existing.get("lat", 0.0)), float(existing.get("lng", 0.0)), float(event.get("lat", 0.0)), float(event.get("lng", 0.0))) > 90:
            continue
        old_norm = normalize_desc(existing.get("desc", ""))
        overlap = len(set(new_norm.split()) & set(old_norm.split()))
        if overlap >= 4:
            return incident_id
    return None


def push_event_buffer(event: dict):
    import main as _m
    _m.events_buffer.append({
        "type": event.get("type"),
        "desc": event.get("desc"),
        "source": _extract_source(event),
    })
    if len(_m.events_buffer) > 80:
        _m.events_buffer[:] = _m.events_buffer[-80:]


def persist_event_v2_pg(event: dict):
    import main as _m
    import v2_store
    v2_store.persist_event_v2_pg(
        event,
        database_url=_m.DATABASE_URL,
        psycopg_mod=_m.psycopg,
        extract_source=_extract_source,
        now_iso=utc_now_iso,
    )


async def ingest_event(event: dict):
    """Centralized ingest path: dedup, persistence, history, broadcast."""
    import main as _m
    with _m.incident_lock:
        merge_id = should_merge_with_existing(event)
        if merge_id:
            _m.metrics["dedup_dropped"] += 1
            existing = _m.incident_index.get(merge_id)
            if existing:
                old_sources = set(existing.get("corroborating_sources", []))
                old_sources.add(_extract_source(event))
                existing["corroborating_sources"] = sorted(old_sources)
                existing["confidence_score"] = min(100, int(existing.get("confidence_score", 45)) + 5)
                existing["confidence_reason"] = f"Merged duplicate reports ({len(old_sources)} sources)"
                persist_event(existing)
                persist_event_v2_pg(existing)
            return

        incident_id = build_incident_id(event)
        event["incident_id"] = incident_id
        _m.incident_index[incident_id] = event

    _m.events_history.append(event)
    if len(_m.events_history) > 1200:
        _m.events_history[:] = _m.events_history[-1200:]

    persist_event(event)
    persist_event_v2_pg(event)
    asyncio.create_task(_sync_event_to_graph_async(event))
    if event.get("video_url"):
        event_id = str(event.get("id", ""))
        if event_id and event_id not in _m._media_job_state:
            _m._media_job_state[event_id] = {"status": "queued", "updated_at": utc_now_iso()}
            await _m._media_jobs.put({"event_id": event_id, "event": event})
    push_event_buffer(event)
    await _m.manager.broadcast({"type": "NEW_EVENT", "data": event})
    await _m.manager.broadcast(
        {
            "type": "NEW_EVENT_DIFF",
            "data": {
                "id": event.get("id"),
                "incident_id": event.get("incident_id"),
                "type": event.get("type"),
                "source": _extract_source(event),
                "lat": event.get("lat"),
                "lng": event.get("lng"),
                "timestamp": event.get("timestamp"),
            },
        }
    )
