"""
Local Ollama AI analyst endpoint — runs Llama 3 on local GPU
"""
import os
import json
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Recent events buffer (shared reference from main.py — set externally)
recent_events_buffer: list = []

async def ensure_ollama_model():
    """Ensure the specified model is pulled into Ollama before use."""
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            print(f"[OLLAMA] Checking model '{OLLAMA_MODEL}'...")
            base_url = OLLAMA_URL.rsplit("/api/", 1)[0]
            resp = await client.post(
                f"{base_url}/api/pull",
                json={"name": OLLAMA_MODEL},
                timeout=600
            )
            # stream the pull response just to keep connection alive or ignore
            print(f"[OLLAMA] Model '{OLLAMA_MODEL}' ready.")
    except Exception as e:
        print(f"[OLLAMA] Warning: Failed to ping/pull model: {e}")

async def generate_analyst_report(events_buffer: list) -> dict:
    """Call local Ollama to generate an intel report from recent events, localized to lang."""
    if not events_buffer:
        return {
            "summary": "No recent events to analyze. Waiting for incoming feeds.",
            "threat_level": "LOW",
            "key_developments": ["Monitoring active..."],
            "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
            "model": OLLAMA_MODEL,
        }

    # Build context from recent events
    event_text = "\n".join([
        f"- [{e.get('type', 'UNKNOWN')}] {e.get('desc', '')} (Source: {e.get('source', '')})"
        for e in events_buffer[-20:]  # Last 20 events
    ])

    prompt = f"""You are an elite military and geopolitical intelligence analyst.
Based on the following OSINT events collected in the last few minutes, provide a concise intelligence briefing.

RECENT EVENTS:
{event_text}

Provide your response ONLY as valid JSON matching this exact structure:
{{
  "summary": "2-3 sentence tactical summary of the current situation",
  "threat_level": "LOW", // MUST be one of: LOW, MEDIUM, HIGH, CRITICAL
  "key_developments": ["development 1", "development 2", "development 3"]
}}

Do not include any markdown formatting, explanations, or notes outside the JSON structure. Respond ONLY with JSON."""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("response", "{}")
            
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.lower().startswith("json"):
                    content = content[4:].strip()

            result = json.loads(content)
            
            # Ensure required fields
            result.setdefault("summary", "Analysis failed to produce summary.")
            result.setdefault("threat_level", "MEDIUM")
            result.setdefault("key_developments", ["Analysis error"])
            
            result["generated_at"] = __import__("datetime").datetime.utcnow().isoformat()
            result["model"] = f"local-{OLLAMA_MODEL}"
            return result
            
    except Exception as e:
        print(f"[ANALYST] Local Ollama Error: {e}")
        return {
            "summary": f"Failed to connect to local Ollama instance ({e}).",
            "threat_level": "UNKNOWN",
            "key_developments": ["Local AI offline or pulling model."],
            "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
            "model": "offline",
        }
