import ipaddress
import os
import re
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import cv2
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="OSINT Local Media Hooks")

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8_float16")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "2"))
WHISPER_MAX_SECONDS = int(os.getenv("WHISPER_MAX_SECONDS", "240"))

_whisper_model = None


class HookRequest(BaseModel):
    media_url: str = ""
    media_path: str = ""


_ALLOWED_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_BLOCKED_HOSTS = re.compile(
    r"^(localhost|.*\.local|.*\.internal)$", re.IGNORECASE
)
_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _validate_url(url: str) -> None:
    if not _ALLOWED_URL_RE.match(url):
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if _BLOCKED_HOSTS.match(host):
        raise HTTPException(status_code=400, detail="Blocked host")
    try:
        addr = ipaddress.ip_address(host)
        for net in _PRIVATE_RANGES:
            if addr in net:
                raise HTTPException(status_code=400, detail="Private/internal IP not allowed")
    except ValueError:
        pass  # hostname, not an IP literal — DNS resolved at fetch time (acceptable)


async def _resolve_media(req: HookRequest) -> Optional[Path]:
    media_path = (req.media_path or "").strip()
    if media_path:
        p = Path(media_path)
        if p.exists() and p.is_file():
            return p
    media_url = (req.media_url or "").strip()
    if not media_url:
        return None
    _validate_url(media_url)
    try:
        suffix = Path(media_url.split("?")[0]).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=False,
            ) as client:
                r = await client.get(media_url)
                if r.status_code != 200:
                    return None
                tmp.write(r.content)
                return Path(tmp.name)
    except HTTPException:
        raise
    except Exception:
        return None


def _load_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    from faster_whisper import WhisperModel

    try:
        _whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
    except Exception:
        _whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device="cpu",
            compute_type="int8",
        )
    return _whisper_model


@app.get("/health")
def health():
    return {
        "status": "ok",
        "whisper_model": WHISPER_MODEL_NAME,
        "whisper_device": WHISPER_DEVICE,
        "whisper_compute_type": WHISPER_COMPUTE_TYPE,
    }


@app.post("/hooks/whisper")
async def whisper_hook(req: HookRequest):
    media_file = await _resolve_media(req)
    if not media_file:
        return {"error": "media_not_found", "transcript": "", "language": ""}
    try:
        model = _load_whisper()
        segments, info = model.transcribe(
            str(media_file),
            beam_size=WHISPER_BEAM_SIZE,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text_parts = []
        total_sec = 0.0
        for seg in segments:
            text_parts.append(seg.text.strip())
            total_sec = float(getattr(seg, "end", total_sec) or total_sec)
            if total_sec >= WHISPER_MAX_SECONDS:
                break
        text = " ".join(x for x in text_parts if x).strip()
        language = str(getattr(info, "language", "") or "")
        if not text:
            return {"error": "empty_transcript", "transcript": "", "language": language}
        return {
            "transcript": text[:3000],
            "language": language,
            "duration_seconds_processed": round(total_sec, 2),
        }
    except Exception as e:
        return {"error": f"whisper_failed:{e}", "transcript": "", "language": ""}
    finally:
        if req.media_url and media_file.exists():
            try:
                media_file.unlink(missing_ok=True)
            except Exception:
                pass


def _deepfake_baseline(video_path: Path) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"score": "0.50", "label": "unverified", "note": "cannot_open_media"}

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    duration = (frame_count / fps) if fps > 0 else 0.0

    sample_blur = []
    sample_diff = []
    prev_gray = None

    step = max(1, frame_count // 30) if frame_count > 0 else 1
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.Laplacian(gray, cv2.CV_64F).var()
            sample_blur.append(float(blur))
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                sample_diff.append(float(np.mean(diff)))
            prev_gray = gray
            if len(sample_blur) >= 30:
                break
        idx += 1

    cap.release()

    avg_blur = float(np.mean(sample_blur)) if sample_blur else 0.0
    avg_diff = float(np.mean(sample_diff)) if sample_diff else 0.0

    # Heuristic authenticity baseline (not a forensic model)
    score = 0.62
    if avg_blur < 25:
        score -= 0.12
    if avg_diff < 6:
        score -= 0.08
    if fps and fps < 12:
        score -= 0.06
    if duration and duration < 2:
        score -= 0.05
    score = max(0.05, min(0.95, score))

    if score >= 0.75:
        label = "likely_authentic"
    elif score >= 0.55:
        label = "uncertain"
    else:
        label = "suspicious"

    return {
        "score": f"{score:.2f}",
        "label": label,
        "note": "baseline_heuristic_not_forensic",
        "meta": {
            "fps": round(fps, 2),
            "duration_sec": round(duration, 2),
            "avg_blur": round(avg_blur, 2),
            "avg_frame_diff": round(avg_diff, 2),
        },
    }


@app.post("/hooks/deepfake")
async def deepfake_hook(req: HookRequest):
    media_file = await _resolve_media(req)
    if not media_file:
        return {"error": "media_not_found", "score": "", "label": ""}
    try:
        result = _deepfake_baseline(media_file)
        return result
    except Exception as e:
        return {"error": f"deepfake_failed:{e}", "score": "", "label": ""}
    finally:
        if req.media_url and media_file.exists():
            try:
                media_file.unlink(missing_ok=True)
            except Exception:
                pass
