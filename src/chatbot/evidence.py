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
    # Institution and place suffixes. Without these, "Mysuru City", "Kalaburagi
    # Rural" and "Forensic Science Laboratory" are all offered as people to
    # check, which makes the extracted-entities panel look careless even though
    # none of them match anything.
    "city", "rural", "urban", "forensic", "science", "laboratory", "division",
    "circle", "taluk", "village", "hospital", "college", "school", "office",
    "department", "government", "act", "section", "report", "statement",
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


_ACCUSED_NAMES: list[str] | None = None


def _accused_names() -> list[str]:
    """Every distinct accused name, loaded once. ~3,500 strings."""
    global _ACCUSED_NAMES
    if _ACCUSED_NAMES is None:
        rows = _fir("SELECT DISTINCT AccusedName FROM Accused WHERE AccusedName IS NOT NULL")
        _ACCUSED_NAMES = [r[0] for r in rows]
    return _ACCUSED_NAMES


def kannada_name_candidates(text: str) -> list[dict]:
    """People named in Kannada script, each with the records that *might* be them.

    Kept apart from `matches` on purpose. A Latin-script name matches a database
    row exactly; a Kannada one is transliterated, and transliteration is
    ambiguous - ಅರುಣ್ ಪಾಟೀಲ್ could be Arun Patil or Arun Patel or Eranna Patil,
    all of whom exist. Presenting a guess as an identification is how the wrong
    person acquires 200 prior FIRs, so the officer is shown the alternatives and
    decides.
    """
    from src.chatbot.kannada_names import extract_kannada_names, match_candidates

    written = extract_kannada_names(text)
    if not written:
        return []
    names = _accused_names()
    out: list[dict] = []
    for kn in written:
        cands = match_candidates(kn, names)
        enriched = []
        for c in cands:
            hit = cross_reference_name(c["name"])
            if not hit or hit["priors"] <= 0:
                continue
            enriched.append({
                "name": hit["matched_name"],
                "priors": hit["priors"],
                "crimes": hit["crimes"][:4],
                "districts": hit["districts"][:3],
                "gangs": hit["gangs"],
                "confidence": c["score"],
            })
        out.append({"written": kn, "candidates": enriched,
                    "ambiguous": len(enriched) > 1})
    return out


def _kn_sys(english: str, kannada: bool) -> str:
    """Kannada-dominant system prompt keeping the "do not invent priors" rule."""
    if not kannada:
        return english
    from src.chatbot.kannada import SYSTEM_KN
    return SYSTEM_KN + "\n\n" + english + "\n\nಟಿಪ್ಪಣಿಯನ್ನು ಕನ್ನಡದಲ್ಲಿ ಬರೆಯಿರಿ."


def analyze(text: str, use_llm: bool = True, kannada: bool = False) -> dict:
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

    # Names written in Kannada script, which the Latin-only regex above cannot
    # see. These stay in their own bucket: they are possibilities, not matches.
    kn_candidates = kannada_name_candidates(text)

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
                # Kannada names must reach the model too. Without them the fact
                # block was empty for a Kannada statement and the note asserted
                # "neither David Mirza nor Arun Patel appears in the database" -
                # the exact opposite of what the panel beside it was showing.
                # They are labelled as unconfirmed so the note cannot upgrade a
                # transliteration into an identification.
                for grp in kn_candidates:
                    if not grp["candidates"]:
                        facts.append(
                            f"- {grp['written']}: ಈ ಹೆಸರಿಗೆ ಹೊಂದುವ ಯಾವುದೇ ದಾಖಲೆ ಇಲ್ಲ."
                            if kannada else
                            f"- {grp['written']} (written in Kannada): no record resembles this name."
                        )
                        continue
                    who = "; ".join(
                        f"{c['name']} ({c['priors']}"
                        + (" ಪೂರ್ವ FIRಗಳು" if kannada else " prior FIRs")
                        + ((", ಗ್ಯಾಂಗ್: " if kannada else ", gang: ") + ", ".join(c["gangs"])
                           if c["gangs"] else "") + ")"
                        for c in grp["candidates"]
                    )
                    # Written in Kannada for a Kannada statement. These lines are
                    # the bulk of what the model reads, so leaving them in English
                    # dropped the human turn to 29% Kannada and the note came back
                    # in English under a Kannada interface.
                    facts.append(
                        f"- {grp['written']} (ದೃಢೀಕರಿಸಿಲ್ಲ): "
                        + ("ಹಲವು ದಾಖಲೆಗಳು ಈ ವ್ಯಕ್ತಿಯದ್ದಾಗಿರಬಹುದು"
                           if grp["ambiguous"] else "ಒಂದು ಸಂಭಾವ್ಯ ದಾಖಲೆ")
                        + f" - {who}. ಇವರಲ್ಲಿ ಯಾರು ಎಂಬುದನ್ನು ಅಧಿಕಾರಿ ದೃಢೀಕರಿಸಬೇಕು."
                        if kannada else
                        f"- {grp['written']} (written in Kannada, NOT confirmed): "
                        f"{'several records could be this person' if grp['ambiguous'] else 'one possible record'}"
                        f" - {who}. The officer must confirm which, if any, is the "
                        f"same person before treating this as a prior record."
                    )
                fact_block = "\n".join(facts) or "No named individual matched a prior FIR."
                # The unconfirmed-match rule is written in the language of the
                # rest of the prompt. Appending it in English to a Kannada system
                # message made English the dominant language of the turn and the
                # note came back in English under a Kannada interface.
                unconfirmed_rule = (
                    "ಯಾವುದೇ ನಮೂದು 'NOT confirmed' ಎಂದು ಗುರುತಿಸಿದ್ದರೆ, ಆ ದಾಖಲೆ ಆ ವ್ಯಕ್ತಿಯದ್ದೇ "
                    "ಆಗಿರಬಹುದು ಮತ್ತು ಪರಿಶೀಲನೆ ಅಗತ್ಯ ಎಂದು ಬರೆಯಿರಿ. ಅವರಿಗೆ ಆ ಪೂರ್ವ ಪ್ರಕರಣಗಳಿವೆ ಎಂದು "
                    "ಹೇಳಬೇಡಿ. ಸಂಭಾವ್ಯ ದಾಖಲೆಗಳಿರುವಾಗ ಆ ವ್ಯಕ್ತಿ ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿ ಇಲ್ಲ ಎಂದು ಹೇಳಬೇಡಿ."
                    if kannada else
                    "Where an entry is marked NOT confirmed, say the record may belong to that "
                    "person and must be verified - never state that they have those priors, and "
                    "never state that a person is absent from the database when candidate records "
                    "are listed for them."
                )
                # "Suspects: X and Y" is what the model produced unprompted from a
                # witness statement. A statement records who a witness says was
                # present; it does not make them suspects, and an AI note is not
                # where that upgrade should happen.
                naming_rule = (
                    "ಹೇಳಿಕೆಯಲ್ಲಿ ಹೆಸರಿಸಿದವರನ್ನು 'ಶಂಕಿತರು' ಅಥವಾ 'ಆರೋಪಿಗಳು' ಎಂದು ಕರೆಯಬೇಡಿ. "
                    "ಸಾಕ್ಷಿ ಹೇಳಿದಂತೆ 'ಹೇಳಿಕೆಯಲ್ಲಿ ಹೆಸರಿಸಲಾದ ವ್ಯಕ್ತಿ' ಎಂದು ಬರೆಯಿರಿ."
                    if kannada else
                    "Do not call anyone named in the statement a suspect or an accused. A "
                    "statement records who a witness says was present; describe them as "
                    "'named in the statement' and leave the characterisation to the officer."
                )
                # Placed last, after the English rules, because the closing
                # instruction is what the model weighs most heavily.
                closing = ("\n\nಸಂಪೂರ್ಣ ಟಿಪ್ಪಣಿಯನ್ನು ಕನ್ನಡದಲ್ಲಿಯೇ ಬರೆಯಿರಿ. "
                           "ಇಂಗ್ಲಿಷ್ ವಾಕ್ಯಗಳನ್ನು ಬಳಸಬೇಡಿ. ಹೆಸರುಗಳನ್ನು ಮಾತ್ರ "
                           "ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿರುವಂತೆ ಬರೆಯಿರಿ." if kannada else "")
                resp = llm.invoke([
                    SystemMessage(content=_kn_sys(
                        "You are KSP Crime Intelligence assisting an investigating officer. From a "
                        "witness/complaint statement and the database cross-reference below, write a "
                        "short (<120 words) investigative note: who in the statement has a criminal "
                        "history, what leads to pursue, and any linked networks. Base facts ONLY on "
                        "the cross-reference; do not invent priors.",
                        kannada) + "\n\n" + unconfirmed_rule
                        + "\n\n" + naming_rule + closing),
                    HumanMessage(content=(
                        f"ಹೇಳಿಕೆ:\n{text[:2000]}\n\nಡೇಟಾಬೇಸ್ ಪರಿಶೀಲನೆ:\n{fact_block}\n\n"
                        "ಕನ್ನಡದಲ್ಲಿ ಸಂಕ್ಷಿಪ್ತ ತನಿಖಾ ಟಿಪ್ಪಣಿ ಬರೆಯಿರಿ."
                        if kannada else
                        f"Statement:\n{text[:2000]}\n\nDatabase cross-reference:\n{fact_block}")),
                ])
                summary = (getattr(resp, "content", "") or "").strip()
                if kannada:
                    # Models slip the odd Bengali or Devanagari letter into
                    # Kannada words; map them back to Kannada.
                    from src.chatbot.kannada import normalize_script
                    summary = normalize_script(summary)
        except Exception:
            summary = ""

    return {
        "transcript": text,
        "entities": {"names_checked": checked, "districts": districts, "crimes": crimes},
        "matches": matches,
        "name_candidates": kn_candidates,
        "summary": summary,
        # Driven only by confirmed matches. An unconfirmed transliteration must
        # never be what escalates a case, or the officer inherits our guess.
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
