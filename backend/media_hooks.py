from typing import Dict, Optional

import httpx


def whisper_transcribe(
    *,
    whisper_url: str,
    media_local_path: Optional[str] = None,
    media_remote_url: Optional[str] = None,
    timeout_sec: int = 40,
) -> Dict[str, str]:
    if not whisper_url:
        return {}
    payload = {"media_url": media_remote_url or "", "media_path": media_local_path or ""}
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(whisper_url, json=payload)
            if r.status_code != 200:
                return {"transcript_error": f"whisper status={r.status_code}"}
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            text = str(data.get("text") or data.get("transcript") or "").strip()
            lang = str(data.get("language") or "")
            if not text:
                return {"transcript_error": "whisper empty transcript"}
            return {"transcript_text": text[:3000], "transcript_language": lang}
    except Exception as e:
        return {"transcript_error": str(e)}


def deepfake_analyze(
    *,
    deepfake_url: str,
    media_local_path: Optional[str] = None,
    media_remote_url: Optional[str] = None,
    timeout_sec: int = 35,
) -> Dict[str, str]:
    if not deepfake_url:
        return {}
    payload = {"media_url": media_remote_url or "", "media_path": media_local_path or ""}
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(deepfake_url, json=payload)
            if r.status_code != 200:
                return {"deepfake_error": f"deepfake status={r.status_code}"}
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            score = data.get("score")
            label = str(data.get("label") or data.get("verdict") or "")
            out: Dict[str, str] = {}
            if score is not None:
                out["deepfake_score"] = str(score)
            if label:
                out["deepfake_label"] = label[:64]
            return out
    except Exception as e:
        return {"deepfake_error": str(e)}
