#!/usr/bin/env python
"""Generate and cache the guide's Kannada narration ahead of time.

The nine explanations are fixed prose, so there is no reason for an officer -
or a judge - to wait five seconds for the speech service the first time each
one is played. Running this once fills the cache; afterwards every clip is read
from disk, which also means the read-aloud keeps working if the network does not.

Run:  python scripts/prewarm_tts.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.tts.gemini_tts import cached_path, synthesize   # noqa: E402

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


def guide_entries() -> list[dict]:
    """Pull the Kannada narration straight out of the page, so this script can
    never drift from what the interface actually says."""
    html = FRONTEND.read_text(encoding="utf-8")
    block = re.search(r"const GUIDE = \[(.*?)\n\];", html, re.S)
    if not block:
        raise SystemExit("GUIDE not found in frontend/index.html")
    out = []
    for m in re.finditer(
        r"kn:\s*\{\s*t:\s*'((?:[^'\\]|\\.)*)',\s*\n\s*what:\s*'((?:[^'\\]|\\.)*)',"
        r"\s*\n\s*does:\s*'((?:[^'\\]|\\.)*)',\s*\n\s*why:\s*'((?:[^'\\]|\\.)*)'",
        block.group(1), re.S,
    ):
        t, what, does, why = (g.replace("\\'", "'") for g in m.groups())
        out.append({"title": t, "script": f"{t}. {what} {does} {why}"})
    return out


def main() -> None:
    entries = guide_entries()
    print(f"{len(entries)} Kannada narrations found in the interface\n")
    if len(entries) != 9:
        print("  warning: expected 9 — check the GUIDE block parsed correctly\n")

    made = cached = failed = 0
    for e in entries:
        if cached_path(e["script"], "kn").exists():
            print(f"  cached     {e['title']}")
            cached += 1
            continue
        wav, note = synthesize(e["script"], "kn")
        if wav is None:
            print(f"  FAILED     {e['title']}  ({note})")
            failed += 1
        else:
            print(f"  generated  {e['title']}  ({len(wav):,} bytes)")
            made += 1

    total = sum(p.stat().st_size for p in cached_path("x", "kn").parent.glob("*.wav"))
    print(f"\ngenerated {made}, already cached {cached}, failed {failed}")
    print(f"cache is {total / 1e6:.1f} MB at data/tts_cache/")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
