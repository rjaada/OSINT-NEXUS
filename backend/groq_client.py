"""
Groq API client — calls deepseek-r1-distill-llama-70b (or any configured model)
for causal intelligence traces. Uses httpx; no groq package required.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_TRACE_TIMEOUT_SEC

logger = logging.getLogger("osint.groq")

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def groq_available() -> bool:
    return bool(GROQ_API_KEY)


def chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """Send a chat request to Groq. Returns assistant message text or None on error."""
    if not GROQ_API_KEY:
        logger.warning("[GROQ] No API key configured")
        return None

    payload: Dict[str, Any] = {
        "model": model or GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    t = timeout if timeout is not None else GROQ_TRACE_TIMEOUT_SEC

    try:
        resp = httpx.post(_GROQ_CHAT_URL, headers=_headers(), json=payload, timeout=t)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as exc:
        logger.error("[GROQ] HTTP %s: %s", exc.response.status_code, exc.response.text[:300])
        return None
    except Exception as exc:
        logger.error("[GROQ] Error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Structured extraction helpers
# ---------------------------------------------------------------------------

_ENTITY_SYSTEM = """You are an OSINT analyst extracting structured entities from conflict/security event descriptions.
Return ONLY valid JSON with these keys (arrays of strings, lowercase):
{
  "actors": [],      // named groups, militaries, factions, organizations, countries
  "weapons": [],     // weapon systems, munitions, vehicle types
  "locations": []    // place names mentioned (cities, regions, countries)
}
No explanation. No markdown. Only JSON."""

_TRACE_SYSTEM = """You are a senior intelligence analyst producing a causal trace of a security event.
You will receive an event description plus its graph context (related events, sources, actors, weapons, locations).
Produce a concise structured analysis in JSON with these exact keys:
{
  "summary": "2-3 sentence plain-language summary of this event in context",
  "preceded_by": ["brief description of what likely or confirmed led to this"],
  "followed_by": ["likely or confirmed consequences / follow-on events"],
  "involved_actors": ["actor names"],
  "weapon_types": ["weapon/system names"],
  "key_locations": ["location names"],
  "confidence": "HIGH|MEDIUM|LOW",
  "confidence_reason": "one sentence explaining confidence level",
  "contradictions": ["any contradictory reporting if present, else empty array"],
  "sources_used": ["source names from context"]
}
Base analysis ONLY on the provided context. Do not invent facts.
Return ONLY valid JSON."""


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract actors, weapons, and locations from event text via Groq."""
    empty: Dict[str, List[str]] = {"actors": [], "weapons": [], "locations": []}
    if not text or not GROQ_API_KEY:
        return empty

    messages = [
        {"role": "system", "content": _ENTITY_SYSTEM},
        {"role": "user", "content": text[:1500]},
    ]
    raw = chat(messages, max_tokens=256, temperature=0.0, timeout=20)
    if not raw:
        return empty
    try:
        # Strip any <think>...</think> reasoning tokens from deepseek-r1
        cleaned = raw
        if "<think>" in cleaned:
            end = cleaned.rfind("</think>")
            cleaned = cleaned[end + 8:].strip() if end != -1 else cleaned
        parsed = json.loads(cleaned)
        return {
            "actors": [str(x).lower() for x in (parsed.get("actors") or [])],
            "weapons": [str(x).lower() for x in (parsed.get("weapons") or [])],
            "locations": [str(x).lower() for x in (parsed.get("locations") or [])],
        }
    except Exception:
        return empty


def trace_event(
    event_description: str,
    graph_context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Given an event description and its subgraph context, ask Groq to produce
    a full causal intelligence trace. Returns parsed JSON dict or None.
    """
    if not GROQ_API_KEY:
        return None

    context_str = json.dumps(graph_context, indent=2, default=str)[:4000]
    messages = [
        {"role": "system", "content": _TRACE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"EVENT DESCRIPTION:\n{event_description[:800]}\n\n"
                f"GRAPH CONTEXT:\n{context_str}"
            ),
        },
    ]
    raw = chat(messages, max_tokens=1024, temperature=0.15)
    if not raw:
        return None
    try:
        cleaned = raw
        if "<think>" in cleaned:
            end = cleaned.rfind("</think>")
            cleaned = cleaned[end + 8:].strip() if end != -1 else cleaned
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if "```" in cleaned:
                cleaned = cleaned[:cleaned.rfind("```")]
            cleaned = cleaned.strip()
        return json.loads(cleaned)
    except Exception:
        return {"raw": raw}
