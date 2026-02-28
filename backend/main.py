"""
OSINT NEXUS — Real-time Intelligence Engine
==============================================
Data sources (all free, no API keys):
  1. OpenSky Network  — live aircraft over Middle East
  2. RSS feeds        — Reuters, AP, Al Jazeera, Times of Israel, BBC
  3. Mock ACLED-style events — conflict events with real-ish coords (fallback)
"""

import asyncio
import json
import re
import uuid
import time
import hashlib
import os
from datetime import datetime, timezone
from typing import List, Optional
import feedparser
import httpx
from analyst import generate_analyst_report
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="OSINT Nexus Engine v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────── Connection Manager ───────────────────────────

class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
        print(f"[WS] +1 client (total {len(self.connections)})")

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
        print(f"[WS] -1 client (total {len(self.connections)})")

    async def broadcast(self, msg: dict):
        text = json.dumps(msg)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()
seen_articles: set = set()      # deduplicate news items
events_buffer: list = []        # last N events for AI analyst
events_history: list = []       # all events with timestamps for backfill
last_aircraft: list = []        # latest aircraft snapshot for stats

# ─────────────────────────────── FLIGHTRADAR24 AIRCRAFT ─────────────────────────────

# Bounding box: Israel, Lebanon, Syria, Iraq, Iran, Yemen, Gulf, Red Sea
# format: y1,y2,x1,x2 (lat_max,lat_min,lng_min,lng_max)
BBOX = "40.0,12.0,30.0,63.0"
FR24_URL = f"https://data-cloud.flightradar24.com/zones/fcgi/feed.js?bounds={BBOX}&faa=1&satellite=1&mlat=1&flarm=1&adsb=1&gnd=0&air=1&vehicles=0&estimated=1&maxage=14400&gliders=0&stats=1"

# Comprehensive military callsign detection
# Sources: ADS-B Exchange, OpenSky community, USAF callsign databases
MILITARY_PREFIXES = {
    # US Air Force – Airlift / Tanker
    "RCH", "REACH", "ATLAS", "JAKE", "SCOTT", "DOVER", "MCCH", "TROP",
    # US Air Force – Combat / Strike
    "FURY", "WOLF", "VIPER", "RAZOR", "SWORD", "DEMON", "RAVEN", "HAWK",
    "EAGLE", "SNAKE", "COBRA", "TIGER", "LANCE", "SABRE", "AVENGER",
    # US Air Force – ISR / Special Missions
    "MAGMA", "SIRIUS", "DARK",  "IRON",  "HUNT",  "JOLLY", "PEDRO",
    "KING",  "GHOST", "CHAOS", "HOBO",  "SPAR",  "VENUS", "SOLAR",
    # US Navy / Marines
    "NAVY",  "VMGR", "TOPGN", "GRIZZLY", "COWBOY", "TOMCAT",
    # NATO / European Military
    "NATO", "NATON", "LFT",  "GAF",   "RAF",   "FAF",   "MEDEVAC",
    "AUST", "CAN",  "BELG",  "DUTCHF",
    # AWACS / AEW
    "SENTRY","AWACS", "HOGAN",
    # Tankers specifically (HUGE red flag when over Middle East)
    "SHELL", "ARCO",  "TEXAC", "QUID",  "JADE",  "ESSO",  "GULF",
    # US Army helicopters
    "DUSTOFF", "MEDEVAC", "LANCER",
    # Special Ops
    "DUKE",  "BEAST",  "FALCN", "VAPOR",
}

def is_military(callsign: str, icao24: str) -> bool:
    if not callsign:
        return False
    cs = callsign.strip().upper()
    return any(cs.startswith(p) for p in MILITARY_PREFIXES)


async def poll_flights():
    """Fetch real aircraft from FlightRadar24 every 8 seconds and broadcast them."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        while True:
            await asyncio.sleep(8)
            try:
                resp = await client.get(FR24_URL)
                if resp.status_code != 200:
                    print(f"[FR24] HTTP {resp.status_code}")
                    continue

                data = resp.json()
                aircraft_list = []

                # Parse FR24 array format. 
                # Key is flight ID, value is array: [icao_hex, lat, lng, track, alt, speed, squawk, radar, type, registration, timestamp, origin, dest, flight_num, on_ground, ...]
                for key, val in data.items():
                    if key in ["full_count", "version", "stats"]:
                        continue
                        
                    if not isinstance(val, list) or len(val) < 14:
                        continue
                        
                    icao        = str(val[0])
                    lat         = val[1]
                    lng         = val[2]
                    heading     = val[3]
                    alt_ft      = val[4]
                    speed_kts   = val[5]
                    ac_type     = str(val[8])
                    callsign    = str(val[13] or val[16] or icao).strip()

                    alt_m   = round(alt_ft * 0.3048)
                    speed_m = round(speed_kts * 0.51444)
                    
                    is_mil = is_military(callsign, icao) or is_military(ac_type, "")

                    aircraft_list.append({
                        "id":       key,  # FR24 flight id
                        "callsign": callsign.upper(),
                        "country":  "Unknown", # FR24 doesn't easily map hex to country in this endpoint
                        "lat":      lat,
                        "lng":      lng,
                        "alt":      alt_m,
                        "speed":    speed_m,
                        "heading":  heading,
                        "military": is_mil,
                    })

                # Cap at 150 planes to avoid nuking frontend performance
                aircraft_list = aircraft_list[:150]

                if aircraft_list:
                    last_aircraft[:] = aircraft_list  # update snapshot for stats
                    await manager.broadcast({
                        "type": "AIRCRAFT_UPDATE",
                        "data": aircraft_list,
                        "ts":   time.time(),
                    })
                    mil_count = sum(1 for a in aircraft_list if a["military"])
                    print(f"[FR24] {len(aircraft_list)} aircraft ({mil_count} military/suspect)")
                    
                    # Add military aircraft to events buffer for AI analyst
                    for ac in aircraft_list:
                        if ac["military"]:
                            events_buffer.append({
                                "type": "MOVEMENT",
                                "desc": f"Military/Target aircraft '{ac['callsign']}' at {ac['alt']}m, heading {ac['heading']}°",
                                "source": "FR24-MIL",
                            })
                    # Keep buffer size sane
                    if len(events_buffer) > 60:
                        events_buffer[:] = events_buffer[-60:]

            except Exception as e:
                print(f"[FR24] Error: {e}")


# ─────────────────────────────── RSS NEWS FEEDS ────────────────────────────────

CONFLICT_KEYWORDS = [
    # English
    "israel", "iran", "hamas", "hezbollah", "idf", "netanyahu",
    "beirut", "gaza", "lebanon", "houthi", "ukraine",
    "strike", "airstrike", "drone", "missile", "attack",
    "war", "military", "troops", "ceasefire", "sanctions",
    "nuclear", "irgc", "mossad", "centcom", "pentagon",
    "tehran", "tel aviv", "rafah", "west bank", "jerusalem",
    "syria", "iraq", "yemen", "red sea", "hormuz", "naval",
    "qatar", "bahrain", "doha", "manama", "al udeid",
    "saudi", "riyadh", "aramco", "jeddah", "dhahran",
    "uae", "abu dhabi", "dubai", "al dhafra",
    "kuwait", "oman", "muscat",
    "gulf", "persian gulf", "strait of hormuz",
    "pakistan", "afghanistan", "islamabad", "kabul",
]

RSS_FEEDS_EN = [
    {
        "name": "Reuters World",
        "url": "https://feeds.reuters.com/Reuters/worldNews",
        "source": "Reuters",
    },
    {
        "name": "Al Jazeera English",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "source": "Al Jazeera",
    },
    {
        "name": "BBC World",
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "source": "BBC News",
    },
    {
        "name": "CBS News World",
        "url": "https://www.cbsnews.com/latest/rss/world",
        "source": "CBS News",
    },
    {
        "name": "The Guardian World",
        "url": "https://www.theguardian.com/world/rss",
        "source": "The Guardian",
    },
    {
        "name": "Times of Israel",
        "url": "https://www.timesofisrael.com/feed",
        "source": "Times of Israel",
    },
]



def is_relevant(entry) -> bool:
    text = (
        getattr(entry, "title", "") + " " +
        getattr(entry, "summary", "") + " " +
        getattr(entry, "description", "")
    ).lower()
    return any(kw in text for kw in CONFLICT_KEYWORDS)

def article_id(entry) -> str:
    key = getattr(entry, "link", "") or getattr(entry, "title", "") or str(entry)
    return hashlib.md5(key.encode()).hexdigest()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

async def geolocate_with_ai(title: str, summary: str) -> Optional[dict]:
    """Pass article text to local LLM to extract precise coordinates and severity."""
    prompt = f"""You are a military intelligence geolocation engine.
Analyze this news event and extract the precise GPS coordinates.
Title: {title}
Summary: {summary}

Respond ONLY with valid JSON in this exact structure:
{{
  "lat": 31.5,
  "lng": 34.5,
  "severity_1_to_10": 5,
  "event_type": "STRIKE" // (STRIKE, MOVEMENT, CLASH, NOTAM)
}}
If no location is found, return dummy coordinates lat:31.5, lng:34.5. Return ONLY JSON."""
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
            )
            data = resp.json().get("response", "{}")
            
            # Clean possible markdown formatting from Llama3 
            data = data.strip()
            if data.startswith("```"):
                data = data.split("```")[1]
                if data.lower().startswith("json"):
                    data = data[4:].strip()

            result = json.loads(data)
            return {
                "lat": float(result.get("lat") if result.get("lat") is not None else 31.5),
                "lng": float(result.get("lng") if result.get("lng") is not None else 34.5),
                "type": result.get("event_type", "CLASH").upper(),
                "severity": int(result.get("severity_1_to_10") if result.get("severity_1_to_10") is not None else 3)
            }
    except Exception as e:
        print(f"[AI GEO] Parsing failed: {e}")
        return None


def classify_event(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    # CRITICAL — highest severity, war-level
    if any(kw in text for kw in [
        "war", "combat operations", "regime change", "nuclear strike",
        "invasion", "declaration of war", "martial law", "all-out",
        "annihilation", "elimination", "carpet bomb",
    ]):
        return "CRITICAL"
    if any(kw in text for kw in ["airstrike", "bombed", "strike", "explosion", "blast", "missile hit"]):
        return "STRIKE"
    if any(kw in text for kw in ["troops", "convoy", "vessel", "fleet", "deploy", "movement", "repositioning", "advance"]):
        return "MOVEMENT"
    if any(kw in text for kw in ["airspace", "notam", "flight ban", "restricted", "gps jam", "naval warning"]):
        return "NOTAM"
    if any(kw in text for kw in ["clash", "gunfire", "battle", "firefight", "exchange", "intercept"]):
        return "CLASH"
    return "CLASH"  # default for relevant news


async def poll_rss():
    """Parse RSS feeds every 90 seconds and broadcast new relevant articles."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        while True:
            for feed_cfg in RSS_FEEDS_EN:
                try:
                    resp = await client.get(feed_cfg["url"])
                    if resp.status_code != 200:
                        continue
                    parsed = feedparser.parse(resp.text)

                    for entry in parsed.entries:
                        aid = article_id(entry)
                        if aid in seen_articles:
                            continue
                        if not is_relevant(entry):
                            continue

                        seen_articles.add(aid)
                        title   = getattr(entry, "title", "No title")
                        summary = getattr(entry, "summary", getattr(entry, "description", ""))
                        # Strip HTML tags from summary
                        summary = re.sub(r"<[^>]+>", "", summary)[:260]

                        # Ask Local AI for precise coords and threat type
                        ai_data = await geolocate_with_ai(title, summary)
                        
                        if ai_data:
                            coords = (ai_data["lat"], ai_data["lng"])
                            etype = "CRITICAL" if ai_data["severity"] >= 8 else ai_data["type"]
                        else:
                            # Fallback if local AI fails/times out
                            coords = (31.5 + (hash(aid) % 10) * 0.3, 35.0 + (hash(aid) % 7) * 0.4)
                            etype = classify_event(title, summary)

                        ts_now = datetime.now(timezone.utc).isoformat()
                        event = {
                            "id":     f"rss_{aid[:10]}",
                            "type":   etype,
                            "desc":   f"[{feed_cfg['source']}] {title}",
                            "lat":    coords[0],
                            "lng":    coords[1],
                            "source": feed_cfg["source"],
                            "timestamp": ts_now,
                        }

                        # Persist to history for backfill
                        events_history.append(event)
                        if len(events_history) > 500:
                            events_history[:] = events_history[-500:]

                        await manager.broadcast({
                            "type": "NEW_EVENT",
                            "data": event,
                        })

                        # Feed event to AI analyst buffer
                        events_buffer.append({
                            "type":   etype,
                            "desc":   f"[{feed_cfg['source']}] {title}",
                            "source": feed_cfg["source"],
                        })
                        if len(events_buffer) > 60:
                            events_buffer[:] = events_buffer[-60:]

                        print(f"[RSS] {feed_cfg['source']}: {title[:60]}")
                        await asyncio.sleep(0.3)  # small stagger

                except Exception as e:
                    pass

            await asyncio.sleep(60)  # poll every 60s for faster news response


# ─────────────────────────────── RED ALERT (PIKUD HAOREF) ─────────────────────

# Israel Home Front Command — real-time rocket/missile alerts
RED_ALERT_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
RED_ALERT_HISTORY_URL = "https://www.oref.org.il/WarningMessages/History/AlertsHistory.json"

# Approximate coordinates for Israeli cities/regions
ISRAEL_CITY_COORDS = {
    "תל אביב": (32.07, 34.78), "tel aviv": (32.07, 34.78),
    "חיפה": (32.79, 34.99), "haifa": (32.79, 34.99),
    "ירושלים": (31.77, 35.21), "jerusalem": (31.77, 35.21),
    "באר שבע": (31.25, 34.79), "beer sheva": (31.25, 34.79),
    "אשדוד": (31.80, 34.65), "ashdod": (31.80, 34.65),
    "אשקלון": (31.66, 34.57), "ashkelon": (31.66, 34.57),
    "נתניה": (32.33, 34.86), "netanya": (32.33, 34.86),
    "שדרות": (31.52, 34.60), "sderot": (31.52, 34.60),
    "עכו": (32.93, 35.08), "acre": (32.93, 35.08),
    "נהריה": (33.00, 35.09), "nahariya": (33.00, 35.09),
    "קריית שמונה": (33.21, 35.57), "kiryat shmona": (33.21, 35.57),
    "צפת": (32.96, 35.50), "safed": (32.96, 35.50),
    "טבריה": (32.79, 35.53), "tiberias": (32.79, 35.53),
    "עפולה": (32.61, 35.29), "afula": (32.61, 35.29),
    "הרצליה": (32.16, 34.78), "herzliya": (32.16, 34.78),
    "פתח תקווה": (32.09, 34.88), "petah tikva": (32.09, 34.88),
    "ראשון לציון": (31.95, 34.80), "rishon lezion": (31.95, 34.80),
    "רמת גן": (32.07, 34.81), "ramat gan": (32.07, 34.81),
    "מודיעין": (31.90, 35.01), "modiin": (31.90, 35.01),
    "רחובות": (31.90, 34.81), "rehovot": (31.90, 34.81),
    "אילת": (29.56, 34.95), "eilat": (29.56, 34.95),
    "מצפה רמון": (30.61, 34.80), "mitzpe ramon": (30.61, 34.80),
    # Regions / areas
    "עוטף עזה": (31.42, 34.42), "gaza envelope": (31.42, 34.42),
    "גליל עליון": (33.05, 35.50), "upper galilee": (33.05, 35.50),
    "גליל תחתון": (32.75, 35.40), "lower galilee": (32.75, 35.40),
    "גולן": (32.95, 35.75), "golan": (32.95, 35.75),
    "שפלה": (31.70, 34.80), "shfela": (31.70, 34.80),
    "שרון": (32.30, 34.87), "sharon": (32.30, 34.87),
    "נגב": (30.85, 34.78), "negev": (30.85, 34.78),
}

seen_alerts: set = set()

def geolocate_alert(city: str) -> tuple:
    """Try to match a city/area name to coordinates."""
    lower = city.lower().strip()
    for name, coords in ISRAEL_CITY_COORDS.items():
        if name in lower or lower in name:
            return coords
    # Default to central Israel if unknown
    return (31.77 + (hash(city) % 10) * 0.05, 35.0 + (hash(city) % 5) * 0.05)


async def poll_red_alert():
    """Poll Pikud HaOref (Israel Home Front Command) for real-time rocket alerts every 3s."""
    headers = {
        "Referer": "https://www.oref.org.il/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
    }
    async with httpx.AsyncClient(timeout=5, headers=headers) as client:
        while True:
            await asyncio.sleep(3)
            try:
                resp = await client.get(RED_ALERT_URL)
                if resp.status_code != 200 or not resp.text.strip():
                    continue

                # Response can be JSON or empty
                try:
                    data = resp.json()
                except Exception:
                    continue

                if not data:
                    continue

                # data structure: {"id": "...", "cat": "1", "title": "...", "data": ["city1", "city2"]}
                alert_id = data.get("id", "")
                if alert_id in seen_alerts:
                    continue
                seen_alerts.add(alert_id)

                alert_title = data.get("title", "Red Alert")
                cities = data.get("data", [])
                ts_now = datetime.now(timezone.utc).isoformat()

                for city in cities:
                    coords = geolocate_alert(city)
                    event = {
                        "id":     f"alert_{hashlib.md5(f'{alert_id}_{city}'.encode()).hexdigest()[:10]}",
                        "type":   "STRIKE",
                        "desc":   f"[Red Alert] 🚀 {alert_title}: {city}",
                        "lat":    coords[0],
                        "lng":    coords[1],
                        "source": "Red Alert",
                        "timestamp": ts_now,
                    }

                    events_history.append(event)
                    if len(events_history) > 500:
                        events_history[:] = events_history[-500:]

                    events_buffer.append({
                        "type":   "STRIKE",
                        "desc":   f"[Red Alert] 🚀 {alert_title}: {city}",
                        "source": "Red Alert",
                    })
                    if len(events_buffer) > 60:
                        events_buffer[:] = events_buffer[-60:]

                    await manager.broadcast({
                        "type": "NEW_EVENT",
                        "data": event,
                    })
                    print(f"[RED ALERT] 🚀 {alert_title}: {city}")

                # Keep seen_alerts bounded
                if len(seen_alerts) > 1000:
                    seen_alerts.clear()

            except Exception as e:
                if "timed out" not in str(e).lower():
                    print(f"[RED ALERT] Error: {e}")


# ─────────────────────────────── STARTUP ──────────────────────────────────────

_start_time = time.time()

from analyst import ensure_ollama_model

@app.on_event("startup")
async def startup_event():
    global _start_time
    _start_time = time.time()
    # Trigger local Ollama to pull Llama3 if needed (disabled to prevent streaming memory freeze)
    # asyncio.create_task(ensure_ollama_model())
    
    asyncio.create_task(poll_flights())
    asyncio.create_task(poll_rss())
    asyncio.create_task(poll_red_alert())
    print("[OSINT] Engine started — Local AI + FR24 + RSS + Red Alert pollers running")


@app.get("/")
async def root():
    return {
        "status": "OSINT Engine v2 Running",
        "clients": len(manager.connections),
        "seen_articles": len(seen_articles),
    }




@app.get("/api/health")
async def health():
    return {"status": "ok", "clients": len(manager.connections), "events_buffered": len(events_buffer)}


@app.get("/api/stats")
async def stats():
    """Real-time stats for the dashboard bottom bar."""
    mil_count = sum(1 for a in last_aircraft if a.get("military"))
    critical_count = sum(1 for e in events_history[-100:] if e.get("type") in ("STRIKE", "CRITICAL"))
    return {
        "events_total":    len(events_history),
        "aircraft_tracked": len(last_aircraft),
        "military_aircraft": mil_count,
        "sources_active":   len(RSS_FEEDS_EN),
        "clients":          len(manager.connections),
        "uptime_seconds":   int(time.time() - _start_time),
    }


@app.get("/api/events")
async def get_events(limit: int = 80):
    """Return recent events for backfill on reconnect."""
    limit = min(limit, 200)
    return events_history[-limit:][::-1]  # newest first


@app.get("/api/analyst")
async def analyst_endpoint():
    """Generate an AI intelligence report from the last N events via local Ollama."""
    # Ensure analyst model runs in local instance!
    from analyst import generate_analyst_report
    return await generate_analyst_report(events_buffer)


@app.websocket("/ws/live")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "SYSTEM",
            "message": "Connected to OSINT Nexus — Real-time feeds active",
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
