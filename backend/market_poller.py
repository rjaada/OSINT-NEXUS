"""
Market signal poller — fetches gold, oil (WTI), DXY, and S&P 500 futures
from free public APIs and injects them as MARKET events into the event stream.

These allow the reasoning engine to correlate:
  - Gold up + military strikes = fear trade confirmed
  - Oil spike + Hormuz NOTAM = supply disruption signal
  - DXY down + conflict escalation = safe-haven demand

Sources:
  - Metals: metals-api (free tier) or fallback to open.er-api.com (XAU/USD)
  - Oil/indices: Yahoo Finance unofficial JSON endpoint (no key required)
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

logger = logging.getLogger("osint.market_poller")

MARKET_POLL_INTERVAL_SEC = 300  # every 5 minutes

# Yahoo Finance query URL (no API key needed, public endpoint)
_YF_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"

# Symbol → human label + approximate geo center for map display
_SYMBOLS = {
    "GC=F":  {"label": "Gold Futures",       "unit": "USD/oz",   "lat": 40.7128,  "lng": -74.0060},
    "CL=F":  {"label": "WTI Crude Oil",      "unit": "USD/bbl",  "lat": 29.7604,  "lng": -95.3698},
    "DX-Y.NYB": {"label": "US Dollar Index", "unit": "index",    "lat": 40.7128,  "lng": -74.0060},
    "^GSPC": {"label": "S&P 500",            "unit": "index",    "lat": 40.7128,  "lng": -74.0060},
    "BZ=F":  {"label": "Brent Crude",        "unit": "USD/bbl",  "lat": 51.5074,  "lng": -0.1278},
}

# Thresholds: % change that makes this "notable"
_ALERT_THRESHOLD_PCT = 1.0  # flag if ±1% move in one session


async def _fetch_symbol(client: httpx.AsyncClient, symbol: str) -> Optional[dict]:
    """Fetch latest price + % change for one symbol from Yahoo Finance."""
    url = _YF_BASE.format(symbol=symbol)
    try:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        meta = data["chart"]["result"][0]["meta"]
        price = float(meta.get("regularMarketPrice") or 0)
        prev_close = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
        pct_change = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
        return {
            "price": round(price, 4),
            "prev_close": round(prev_close, 4),
            "pct_change": round(pct_change, 3),
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("exchangeName", ""),
            "market_state": meta.get("marketState", ""),
        }
    except Exception as exc:
        logger.debug("[MARKET] %s fetch failed: %s", symbol, exc)
        return None


def _make_market_event(
    symbol: str,
    info: dict,
    price_data: dict,
    now_iso: str,
) -> dict:
    """Build a market event dict compatible with ingest_event."""
    pct = price_data["pct_change"]
    direction = "▲" if pct >= 0 else "▼"
    abs_pct = abs(pct)
    notable = abs_pct >= _ALERT_THRESHOLD_PCT

    desc = (
        f"{info['label']}: {direction}{abs_pct:.2f}% "
        f"(${price_data['price']:,.2f} {info['unit']}) "
        f"[{price_data['market_state']}]"
    )

    # Severity: notable moves are MOVEMENT type, small moves are INFO
    event_type = "MOVEMENT" if notable else "INFO"
    confidence_score = 90 if notable else 70  # market data is highly reliable

    # Unique ID per symbol per 5-minute bucket
    bucket = now_iso[:15]  # YYYY-MM-DDTHH:MM truncated
    uid = hashlib.md5(f"market_{symbol}_{bucket}".encode()).hexdigest()[:10]

    return {
        "id": f"mkt_{uid}",
        "type": event_type,
        "source": "Market Data",
        "source_name": "Market Data",
        "timestamp": now_iso,
        "lat": info["lat"],
        "lng": info["lng"],
        "desc": desc,
        "confidence_score": confidence_score,
        "confidence": "HIGH",
        "confidence_reason": f"Live market feed — {price_data['exchange']}",
        "observed_facts": [
            f"{info['label']} at ${price_data['price']:,.2f} {info['unit']}",
            f"Change from previous close: {pct:+.2f}%",
        ],
        "model_inference": (
            [f"Notable {direction} move — potential geopolitical risk signal"] if notable else []
        ),
        "market_symbol": symbol,
        "market_price": price_data["price"],
        "market_pct_change": pct,
        "market_unit": info["unit"],
        "insufficient_evidence": False,
    }


async def poll_markets(
    ingest_fn: Callable,
    now_iso_fn: Callable[[], str],
    interval_sec: int = MARKET_POLL_INTERVAL_SEC,
) -> None:
    """
    Background coroutine: polls market symbols every `interval_sec` seconds,
    injects notable moves (and all moves for the reasoning engine) as events.
    """
    await asyncio.sleep(60)  # let other pollers start first

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; research/1.0)"},
        follow_redirects=True,
    ) as client:
        while True:
            try:
                now = now_iso_fn()
                for symbol, info in _SYMBOLS.items():
                    price_data = await _fetch_symbol(client, symbol)
                    if price_data is None:
                        continue
                    # Only ingest notable moves to avoid flooding
                    if abs(price_data["pct_change"]) >= 0.3:
                        event = _make_market_event(symbol, info, price_data, now)
                        try:
                            await ingest_fn(event)
                            logger.debug(
                                "[MARKET] %s %+.2f%% → ingested",
                                info["label"], price_data["pct_change"],
                            )
                        except Exception as exc:
                            logger.warning("[MARKET] ingest failed for %s: %s", symbol, exc)
                    await asyncio.sleep(1)  # gentle rate limiting between symbols
            except Exception as exc:
                logger.error("[MARKET] poll_markets error: %s", exc)

            await asyncio.sleep(interval_sec)
