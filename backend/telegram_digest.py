"""
Telegram daily digest — sends SITREP summary 3× per day (06:00, 12:00, 18:00 UTC).
English message first, then full Arabic translation via Groq.

No startup ping — only fires at the scheduled times.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

import httpx

logger = logging.getLogger("osint.telegram_digest")

_TG_API = "https://api.telegram.org/bot{token}/sendMessage"

# Default send times (UTC hours). Override via TG_DIGEST_HOURS_UTC env var (comma-separated).
DEFAULT_SEND_HOURS = [6, 12, 18]


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

    chain = sitrep.get("causal_chain") or []
    if chain:
        lines.append("")
        lines.append("🔗 <b>CAUSAL CHAIN</b>")
        for i, step in enumerate(chain, 1):
            lines.append(f"  {i}. {step}")

    watches = sitrep.get("watch_items") or []
    if watches:
        lines.append("")
        lines.append("👁 <b>WATCH NEXT</b>")
        for w in watches:
            lines.append(f"  • <b>{w.get('item','')}</b> [{w.get('timeframe','')}]")
            lines.append(f"    {w.get('why','')}")

    if contradictions:
        lines.append("")
        lines.append(f"⚠️ <b>{contradictions} CONTRADICTIONS DETECTED</b> — cross-check sources")

    actors = sitrep.get("dominant_actors") or []
    locations = sitrep.get("key_locations") or []
    if actors or locations:
        lines.append("")
        if actors:
            lines.append(f"👤 Actors: {', '.join(actors)}")
        if locations:
            lines.append(f"📍 Locations: {', '.join(locations)}")

    parallel = sitrep.get("historical_parallel", "")
    if parallel and "no clear" not in parallel.lower():
        lines.append("")
        lines.append(f"📚 <i>{parallel}</i>")

    lines.append("")
    lines.append("——")
    lines.append("🔗 <i>Open OSINT Nexus → SITREP tab for full report</i>")

    return "\n".join(lines)


def _translate_to_arabic(text: str) -> Optional[str]:
    """Use Groq to translate the English SITREP message to full Arabic."""
    try:
        import groq_client
        if not groq_client.groq_available():
            return None

        prompt = f"""Translate the following intelligence report from English to Arabic.
Keep all HTML tags (<b>, <i>) exactly as they are.
Keep emojis exactly as they are.
Keep dates, numbers, and proper nouns as-is.
Translate ALL English text to natural, formal Arabic suitable for intelligence reports.
Return ONLY the translated text, nothing else.

TEXT:
{text}"""

        result = groq_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
            timeout=30,
        )
        return result
    except Exception as exc:
        logger.warning("[TG_DIGEST] Arabic translation failed: %s", exc)
        return None


async def send_digest_now(
    token: str,
    chat_id: str,
    load_latest_fn: Callable,
) -> bool:
    """Send current SITREP — English first, then full Arabic translation."""
    result = load_latest_fn("sitrep")
    if not result:
        text_en = "⚠️ <b>OSINT NEXUS</b>\n\nNo SITREP available yet. Check back after the first cycle."
    else:
        report = result.get("report") or {}
        text_en = _format_sitrep(report)

    ok_en = await _send(token, chat_id, text_en)
    await asyncio.sleep(1)

    # Translate the English message to full Arabic via Groq
    text_ar = await asyncio.to_thread(_translate_to_arabic, text_en)
    if not text_ar:
        # Fallback header if translation fails
        text_ar = "⚠️ <b>نيكسوس للاستخبارات</b>\n\nتعذّر ترجمة التقرير. يرجى مراجعة النسخة الإنجليزية."

    ok_ar = await _send(token, chat_id, text_ar)
    return ok_en and ok_ar


def _seconds_until_next(send_hours: List[int]) -> float:
    """Return seconds until the next scheduled send time."""
    now = datetime.now(timezone.utc)
    candidates = []
    for hour in send_hours:
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        candidates.append(target)
    next_target = min(candidates)
    return (next_target - now).total_seconds()


async def poll_daily_digest(
    token: str,
    chat_id: str,
    load_latest_fn: Callable,
    send_hours_utc: Optional[List[int]] = None,
    # Legacy param kept for backward compat — ignored if send_hours_utc is set
    send_hour_utc: int = 6,
) -> None:
    """
    Background task: sends digest at each hour in send_hours_utc (UTC).
    Default: 06:00, 12:00, 18:00 UTC (3× per day).
    No startup ping — only fires at scheduled times.
    """
    if not token or not chat_id:
        logger.warning("[TG_DIGEST] Token or chat_id not set — digest disabled")
        return

    hours = send_hours_utc if send_hours_utc else DEFAULT_SEND_HOURS
    logger.info("[TG_DIGEST] Scheduled at %s UTC daily", hours)

    while True:
        wait_sec = _seconds_until_next(hours)
        next_dt = datetime.now(timezone.utc) + timedelta(seconds=wait_sec)
        logger.info(
            "[TG_DIGEST] Next digest in %.0f minutes at %s UTC",
            wait_sec / 60,
            next_dt.strftime("%H:%M"),
        )
        await asyncio.sleep(wait_sec)

        logger.info("[TG_DIGEST] Sending scheduled digest")
        ok = await send_digest_now(token, chat_id, load_latest_fn)
        logger.info("[TG_DIGEST] Digest sent: %s", ok)
        await asyncio.sleep(90)  # prevent double-send within same window
