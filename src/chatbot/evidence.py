"""Evidence Intelligence — turn an unstructured statement (typed, document, or audio)
into linked crime intelligence by extracting entities and cross-referencing the FIR DB.

No heavy dependencies: document text via pypdf/python-docx, audio via Groq Whisper,
entity grounding via the same vocab used by the RAG. Works fully without an LLM;
an optional LLM synthesis adds a narrative when a provider is available.
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path

import duckdb

from src.chatbot.rag.schema_live import match_districts, match_crime_heads

_DATA = Path(__file__).resolve().parents[2] / "data"


def _fir_path() -> str | None:
    for p in (_DATA / "ksp_fir.duckdb", _DATA / "unified" / "ksp_fir.duckdb"):
        if p.exists():
            return str(p)
    return None


def _fir(sql: str, params: list | None = None):
    path = _fir_path()
    if not path:
        return []
    con = duckdb.connect(path, read_only=True, config={"enable_external_access": False})
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


# ── Text extraction from uploads ────────────────────────────────────────────
def _groq_key() -> str:
    k = (os.getenv("GROQ_API_KEY") or "").strip()
    if k:
        return k
    alt = (os.getenv("OPENAI_API_KEY") or "").strip()
    return alt if alt.startswith("gsk_") else ""


def transcribe_audio(raw: bytes, filename: str, content_type: str, language: str = "en") -> tuple[str, str]:
    """Return (text, note). Uses Groq Whisper; degrades gracefully if unavailable."""
    key = _groq_key()
    if not key:
        return "", "Audio transcription needs a Groq API key (Whisper). Paste the statement text instead."
    import requests
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (filename or "audio.wav", raw, content_type or "audio/wav")},
            data={"model": os.getenv("STT_MODEL", "whisper-large-v3"),
                  "language": "kn" if language == "kn" else "en", "response_format": "json"},
            timeout=45,
        )
        if r.status_code == 200:
            return (r.json().get("text") or "").strip(), ""
        return "", f"Transcription unavailable (status {r.status_code})."
    except Exception:
        return "", "Could not reach the transcription service."


def extract_text(filename: str, raw: bytes) -> tuple[str, str]:
    """Return (text, note) from an uploaded file by type."""
    name = (filename or "").lower()
    if name.endswith((".txt", ".md", ".csv")):
        return raw.decode("utf-8", errors="ignore"), ""
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((p.extract_text() or "") for p in reader.pages), ""
        except Exception:
            return "", "Could not read the PDF."
    if name.endswith((".docx", ".doc")):
        try:
            import docx
            d = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in d.paragraphs), ""
        except Exception:
            return "", "Could not read the document."
    if name.endswith((".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac")):
        return transcribe_audio(raw, filename, "audio/" + name.split(".")[-1])
    # Unknown: try plain text
    try:
        return raw.decode("utf-8", errors="ignore"), ""
    except Exception:
        return "", "Unsupported file type. Use text, PDF, DOCX, or audio."


# ── Entity extraction + DB cross-reference ──────────────────────────────────
_NAME_STOP = {
    "police", "station", "district", "fir", "case", "crime", "court", "the", "sub",
    "inspector", "officer", "sir", "madam", "karnataka", "state", "india", "road",
    "near", "house", "shop", "bank", "market", "temple", "mr", "mrs", "smt", "shri",
}
# [^\S\n] is "whitespace but not a newline": plain \s let a name run across a line
# break and swallow the next word ("Lokesh\nDate", "Suresh Gowda\nSd").
_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:[^\S\n]+[A-Z][a-z]+){1,2})\b")


def extract_names(text: str) -> list[str]:
    cands: list[str] = []
    for m in _NAME_RE.finditer(text):
        phrase = m.group(1).strip()
        words = phrase.split()
        if any(w.lower() in _NAME_STOP for w in words):
            continue
        if phrase not in cands:
            cands.append(phrase)
    return cands[:12]


def cross_reference_name(name: str) -> dict | None:
    like = f"%{name}%"
    rows = _fir(
        """SELECT a.AccusedName AS name, COUNT(DISTINCT a.CaseMasterID) AS priors,
                  STRING_AGG(DISTINCT csh.CrimeHeadName, ', ') AS crimes,
                  STRING_AGG(DISTINCT d.DistrictName, ', ') AS districts
           FROM Accused a
           JOIN CaseMaster cm ON a.CaseMasterID = cm.CaseMasterID
           JOIN Unit u ON cm.PoliceStationID = u.UnitID
           JOIN District d ON u.DistrictID = d.DistrictID
           JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
           WHERE a.AccusedName ILIKE ?
           GROUP BY a.AccusedName ORDER BY priors DESC LIMIT 1""",
        [like],
    )
    if not rows:
        return None
    r = rows[0]
    gangs = _fir(
        """SELECT DISTINCT g.GangName FROM AccusedGangLink agl
           JOIN CrimeGang g ON agl.GangID = g.GangID
           JOIN Accused a ON agl.AccusedMasterID = a.AccusedMasterID
           WHERE a.AccusedName ILIKE ? LIMIT 3""",
        [like],
    )
    crimes = (r[2] or "").split(", ")
    return {
        "query_name": name,
        "matched_name": r[0],
        "priors": int(r[1]),
        "crimes": crimes[:6],
        "districts": (r[3] or "").split(", ")[:6],
        "gangs": [g[0] for g in gangs],
    }


def analyze(text: str, use_llm: bool = True) -> dict:
    text = (text or "").strip()
    if not text:
        return {"error": "No statement text provided."}

    districts = match_districts(text, _fir_path() or "")
    crimes = match_crime_heads(text, _fir_path() or "")
    names = extract_names(text)

    matches, checked = [], []
    for n in names:
        checked.append(n)
        hit = cross_reference_name(n)
        if hit and hit["priors"] > 0:
            matches.append(hit)

    # Optional LLM investigative note (graceful if no provider / quota)
    summary = ""
    if use_llm:
        try:
            from src.chatbot.llm_config import create_llm
            llm = create_llm(temperature=0.3)
            if llm is not None:
                from langchain_core.messages import HumanMessage, SystemMessage
                facts = []
                for m in matches:
                    facts.append(f"- {m['matched_name']}: {m['priors']} prior FIRs "
                                 f"({', '.join(m['crimes'][:4])}) across {', '.join(m['districts'][:3])}"
                                 + (f"; gang: {', '.join(m['gangs'])}" if m['gangs'] else ""))
                fact_block = "\n".join(facts) or "No named individual matched a prior FIR."
                resp = llm.invoke([
                    SystemMessage(content=(
                        "You are KSP Crime Intelligence assisting an investigating officer. From a "
                        "witness/complaint statement and the database cross-reference below, write a "
                        "short (<120 words) investigative note: who in the statement has a criminal "
                        "history, what leads to pursue, and any linked networks. Base facts ONLY on "
                        "the cross-reference; do not invent priors.")),
                    HumanMessage(content=f"Statement:\n{text[:2000]}\n\nDatabase cross-reference:\n{fact_block}"),
                ])
                summary = (getattr(resp, "content", "") or "").strip()
        except Exception:
            summary = ""

    return {
        "transcript": text,
        "entities": {"names_checked": checked, "districts": districts, "crimes": crimes},
        "matches": matches,
        "summary": summary,
        "high_risk": any(m["priors"] >= 3 for m in matches),
    }


def sample_statement() -> str:
    """A realistic statement pre-seeded with a real repeat-offender name for the demo."""
    row = _fir(
        """SELECT a.AccusedName, COUNT(DISTINCT a.CaseMasterID) n
           FROM Accused a WHERE a.AccusedName IS NOT NULL
           GROUP BY a.AccusedName HAVING COUNT(DISTINCT a.CaseMasterID) >= 5
           ORDER BY n DESC LIMIT 1"""
    )
    name = row[0][0] if row else "Rashid Rao"
    return (
        f"On the night of 12th, near the Mysuru main market, I saw two men snatch a gold chain "
        f"from a woman and flee on a motorcycle. One of them was called {name} by the other. "
        f"I have seen {name} before in a cheating case in Bengaluru. Please register a theft FIR "
        f"and investigate his gang connections."
    )
