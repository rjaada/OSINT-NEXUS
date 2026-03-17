"""
Groq API client — calls deepseek-r1-distill-llama-70b (or any configured model)
for causal intelligence traces. Uses httpx; no groq package required.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_TRACE_TIMEOUT_SEC, OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger("osint.groq")

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def groq_available() -> bool:
    return bool(GROQ_API_KEY)


def _ollama_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: int = 120,
    json_mode: bool = False,
) -> Optional[str]:
    """Fallback: send chat request to local Ollama. Returns text or None."""
    try:
        # For json_mode, inject an assistant prefill starting with '{' to force JSON continuation
        msgs = messages
        if json_mode:
            msgs = list(messages) + [{"role": "assistant", "content": "{"}]
        payload = {
            "model": OLLAMA_MODEL,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        resp = httpx.post(_OLLAMA_CHAT_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        # Restore the prefill prefix that Ollama won't include in response
        return ("{" + content) if json_mode and not content.strip().startswith("{") else content
    except Exception as exc:
        logger.error("[OLLAMA_FALLBACK] Error: %s", exc)
        return None


def chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: Optional[int] = None,
    json_mode: bool = False,
) -> Optional[str]:
    """Send a chat request to Groq, falling back to local Ollama on 429 or failure.

    json_mode=True enforces structured JSON output:
      - Groq: response_format={"type": "json_object"}
      - Ollama: assistant prefill message starting with '{' to force JSON continuation
    """
    t = timeout if timeout is not None else GROQ_TRACE_TIMEOUT_SEC

    if GROQ_API_KEY:
        payload: Dict[str, Any] = {
            "model": model or GROQ_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = httpx.post(_GROQ_CHAT_URL, headers=_headers(), json=payload, timeout=t)
            if resp.status_code == 429:
                logger.warning("[GROQ] Rate limit hit — falling back to local Ollama")
                return _ollama_chat(messages, temperature, max_tokens, json_mode=json_mode)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            logger.error("[GROQ] HTTP %s — falling back to Ollama: %s", exc.response.status_code, exc.response.text[:200])
            return _ollama_chat(messages, temperature, max_tokens, json_mode=json_mode)
        except Exception as exc:
            logger.error("[GROQ] Error — falling back to Ollama: %s", exc)
            return _ollama_chat(messages, temperature, max_tokens, json_mode=json_mode)
    else:
        logger.warning("[GROQ] No API key — using local Ollama directly")
        return _ollama_chat(messages, temperature, max_tokens, json_mode=json_mode)


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
  "confidence": "HIGH|MODERATE|LOW|VERY LOW",
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
    Falls back to Ollama if Groq key is unavailable.
    """
    import re

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

    # Robust extraction: strip <think> blocks, markdown fences, find outermost {}
    _ICD203_TRACE = {
        "HIGH": ("HIGH", "Almost certainly"),
        "MODERATE": ("MODERATE", "Very likely"),
        "MEDIUM": ("MODERATE", "Very likely"),
        "LOW": ("LOW", "Likely"),
        "VERY LOW": ("VERY LOW", "Unlikely"),
    }
    try:
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if "```" in text:
            text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
        result = json.loads(text)
        if isinstance(result, dict):
            conf_key = str(result.get("confidence", "LOW")).upper().strip()
            icd_level, icd_phrase = _ICD203_TRACE.get(conf_key, ("LOW", "Likely"))
            result["icd203_level"] = icd_level
            result["icd203_phrase"] = icd_phrase
        return result
    except Exception:
        return None
