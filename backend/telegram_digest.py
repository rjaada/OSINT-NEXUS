"""
Telegram daily digest — sends SITREP summary every day at 0600 UTC.
Also supports on-demand sends via send_digest_now().
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

logger = logging.getLogger("osint.telegram_digest")

_TG_API = "https://api.telegram.org/bot{token}/sendMessage"


async def _send(token: str, chat_id: str, text: str) -> bool:
    url = _TG_API.format(token=token)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.error("[TG_DIGEST] send failed: %s", exc)
        return False


def _format_sitrep(report: dict) -> str:
    sitrep = report.get("sitrep") or {}
    if not sitrep:
        return "⚠️ <b>OSINT NEXUS — SITREP</b>\n\nNo intelligence picture available yet."

    confidence = sitrep.get("confidence", "?")
    conf_icon = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(confidence, "⚪")

    quality = report.get("data_quality", "?")
    events = report.get("event_count", 0)
    cluster = report.get("dominant_cluster_size", 0)
    contradictions = len(report.get("contradictions") or [])
    gen_at = str(report.get("generated_at", ""))[:16].replace("T", " ")

    lines = [
        "🛰 <b>OSINT NEXUS — DAILY SITREP</b>",
        f"📅 {gen_at} UTC | {events} events | {quality.upper()} DATA",
        "",
        f"{conf_icon} <b>{sitrep.get('headline', 'No headline')}</b>",
        f"Confidence: <b>{confidence}</b> — {sitrep.get('confidence_reason', '')}",
        "",
        "📋 <b>SITUATION</b>",
        sitrep.get("what_happened", ""),
        "",
        "⚡ <b>WHY IT MATTERS</b>",
        sitrep.get("why_it_matters", ""),
    ]

    # Causal chain
    chain = sitrep.get("causal_chain") or []
    if chain:
        lines.append("")
        lines.append("🔗 <b>CAUSAL CHAIN</b>")
        for i, step in enumerate(chain, 1):
            lines.append(f"  {i}. {step}")

    # Watch items
    watches = sitrep.get("watch_items") or []
    if watches:
        lines.append("")
        lines.append("👁 <b>WATCH NEXT</b>")
        for w in watches:
            lines.append(f"  • <b>{w.get('item','')}</b> [{w.get('timeframe','')}]")
            lines.append(f"    {w.get('why','')}")

    # Contradictions
    if contradictions:
        lines.append("")
        lines.append(f"⚠️ <b>{contradictions} CONTRADICTIONS DETECTED</b> — cross-check sources")

    # Actors / locations
    actors = sitrep.get("dominant_actors") or []
    locations = sitrep.get("key_locations") or []
    if actors or locations:
        lines.append("")
        if actors:
            lines.append(f"👤 Actors: {', '.join(actors)}")
        if locations:
            lines.append(f"📍 Locations: {', '.join(locations)}")

    # Historical parallel
    parallel = sitrep.get("historical_parallel", "")
    if parallel and "no clear" not in parallel.lower():
        lines.append("")
        lines.append(f"📚 <i>{parallel}</i>")

    lines.append("")
    lines.append("——")
    lines.append("🔗 <i>Open OSINT Nexus → SITREP tab for full report</i>")

    return "\n".join(lines)


async def send_digest_now(
    token: str,
    chat_id: str,
    load_latest_fn: Callable,
) -> bool:
    """Send the current SITREP immediately. Called on-demand or by scheduler."""
    result = load_latest_fn("sitrep")
    if not result:
        text = "⚠️ <b>OSINT NEXUS</b>\n\nNo SITREP available yet. Check back after the first cycle."
    else:
        report = result.get("report") or {}
        text = _format_sitrep(report)

    return await _send(token, chat_id, text)


async def poll_daily_digest(
    token: str,
    chat_id: str,
    load_latest_fn: Callable,
    send_hour_utc: int = 6,
) -> None:
    """
    Background task: sends digest every day at send_hour_utc:00 UTC.
    Also sends one on startup (after 3 min) so you know it's working.
    """
    if not token or not chat_id:
        logger.warning("[TG_DIGEST] Token or chat_id not set — digest disabled")
        return

    # Startup ping after 3 minutes
    await asyncio.sleep(180)
    logger.info("[TG_DIGEST] Sending startup digest")
    await send_digest_now(token, chat_id, load_latest_fn)

    while True:
        now = datetime.now(timezone.utc)
        # Seconds until next send_hour:00 UTC
        target_hour = now.replace(hour=send_hour_utc, minute=0, second=0, microsecond=0)
        if now >= target_hour:
            # Already past today's send time — wait for tomorrow
            from datetime import timedelta
            target_hour = target_hour + timedelta(days=1)
        wait_sec = (target_hour - now).total_seconds()
        logger.info("[TG_DIGEST] Next digest in %.0f minutes", wait_sec / 60)
        await asyncio.sleep(wait_sec)

        logger.info("[TG_DIGEST] Sending daily digest")
        ok = await send_digest_now(token, chat_id, load_latest_fn)
        logger.info("[TG_DIGEST] Digest sent: %s", ok)
        await asyncio.sleep(60)  # prevent double-send within same minute
