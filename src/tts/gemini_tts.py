"""Kannada speech, generated server-side and cached.

The browser's own speech engine reads the interface aloud for free, but only in
languages the operating system has a voice for. Windows ships English voices
and nothing else unless a language pack is added, so on most machines the
Kannada read-aloud was silent — which, in a product whose whole claim is that it
works in Kannada, is the wrong thing to be missing.

Gemini generates the audio instead, so Kannada speech does not depend on what
the officer's machine happens to have installed.

Every clip is cached on disk under a hash of its text. The guide's narration is
fixed prose, so after the first play it is served from disk: no API call, no
quota, no wait, and it keeps working if the network does not.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import urllib.error
import urllib.request
from pathlib import Path

_CACHE = Path(__file__).resolve().parents[2] / "data" / "tts_cache"

# Gemini returns headerless 16-bit signed PCM at this rate. A browser cannot
# play that from an <audio> element, so it is wrapped as a WAV before sending.
_SAMPLE_RATE = 24000
_MODEL = "gemini-2.5-flash-preview-tts"
# Kore reads Kannada clearly. The voice is not language-specific — the model
# adapts it to the script it is given.
_VOICE = "Kore"

MAX_CHARS = 900


def _key(text: str, lang: str) -> str:
    return hashlib.sha256(f"{lang}|{_VOICE}|{text}".encode("utf-8")).hexdigest()[:32]


def _wav(pcm: bytes, rate: int = _SAMPLE_RATE) -> bytes:
    """Wrap raw mono 16-bit PCM in a WAV container."""
    return (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )


def _api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def cached_path(text: str, lang: str) -> Path:
    return _CACHE / f"{_key(text, lang)}.wav"


def synthesize(text: str, lang: str = "kn") -> tuple[bytes | None, str]:
    """Return (wav_bytes, note). A None result is a reason to fall silent, not
    to raise: speech is an enhancement and must never break the page."""
    text = (text or "").strip()
    if not text:
        return None, "empty text"
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]

    path = cached_path(text, lang)
    if path.exists():
        return path.read_bytes(), "cache"

    key = _api_key()
    if not key:
        return None, "no Gemini API key configured"

    body = json.dumps({
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": _VOICE}}
            },
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:generateContent?key={key}",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        try:
            detail = json.loads(detail)["error"]["message"]
        except Exception:
            pass
        return None, f"speech service returned {e.code}: {detail[:120]}"
    except Exception as e:
        return None, f"could not reach the speech service ({type(e).__name__})"

    try:
        parts = payload["candidates"][0]["content"]["parts"]
        inline = next(p["inlineData"] for p in parts if "inlineData" in p)
        pcm = base64.b64decode(inline["data"])
    except Exception:
        return None, "speech service returned no audio"

    wav = _wav(pcm)
    try:
        _CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav)
    except Exception:
        pass          # cache is an optimisation, not a requirement
    return wav, "generated"
