"""Local Ollama AI analyst endpoint — strict structured output with guardrails."""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


async def ensure_ollama_model():
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            base_url = OLLAMA_URL.rsplit("/api/", 1)[0]
            await client.post(f"{base_url}/api/pull", json={"name": OLLAMA_MODEL}, timeout=600)
            print(f"[OLLAMA] Model '{OLLAMA_MODEL}' ready.")
    except Exception as e:
        print(f"[OLLAMA] Warning: Failed to ping/pull model: {e}")


def _safe_default(msg: str = "Insufficient evidence to produce reliable analyst brief.") -> Dict[str, Any]:
    return {
        "summary": msg,
        "threat_level": "MEDIUM",
        "key_developments": ["Insufficient evidence"],
        "insufficient_evidence": True,
        "generated_at": datetime.utcnow().isoformat(),
        "model": f"local-{OLLAMA_MODEL}",
    }


async def _call_ollama_json(prompt: str, retries: int = 2) -> Optional[dict]:
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1},
                    },
                )
                resp.raise_for_status()
                raw = str(resp.json().get("response", "{}")).strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    raw = raw.replace("json", "", 1).strip()
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            if attempt == retries:
                print(f"[ANALYST] Ollama parse failed: {e}")
    return None


def _normalize_threat(level: str) -> str:
    level = (level or "").upper().strip()
    if level in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        return level
    return "MEDIUM"


async def generate_analyst_report(events_buffer: List[dict]) -> Dict[str, Any]:
    if not events_buffer:
        return _safe_default("No recent events to analyze. Waiting for incoming feeds.")

    event_text = "\n".join(
        [f"- [{e.get('type', 'UNKNOWN')}] {e.get('desc', '')} (Source: {e.get('source', '')})" for e in events_buffer[-30:]]
    )

    prompt = f"""You are an intelligence analyst assistant for a monitoring dashboard.
Return ONLY strict JSON with this schema:
{{
  "summary": "2-3 sentence tactical summary",
  "threat_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "key_developments": ["item1", "item2", "item3"],
  "insufficient_evidence": true|false
}}
Rules:
- If evidence is weak or contradictory, set insufficient_evidence=true.
- If insufficient_evidence=true, keep threat_level at MEDIUM unless explicit official warning exists in events.
- No markdown and no extra keys.

RECENT EVENTS:
{event_text}
"""

    data = await _call_ollama_json(prompt, retries=2)
    if not data:
        return _safe_default("Failed to connect to local Ollama instance.")

    summary = str(data.get("summary", "")).strip() or "Insufficient evidence to produce reliable analyst brief."
    threat = _normalize_threat(str(data.get("threat_level", "MEDIUM")))
    key_developments = data.get("key_developments") if isinstance(data.get("key_developments"), list) else []
    key_developments = [str(x)[:200] for x in key_developments[:5]] or ["Insufficient evidence"]
    insufficient = bool(data.get("insufficient_evidence", False))

    if insufficient and threat in {"HIGH", "CRITICAL"}:
        threat = "MEDIUM"

    return {
        "summary": summary,
        "threat_level": threat,
        "key_developments": key_developments,
        "insufficient_evidence": insufficient,
        "generated_at": datetime.utcnow().isoformat(),
        "model": f"local-{OLLAMA_MODEL}",
    }
