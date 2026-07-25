"""FastAPI backend for KSP Crime Chatbot web UI."""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import duckdb as _duckdb
import pandas as _pd

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT))

from src.chatbot.chat_store import ChatStore
from src.chatbot.doc_store import DocStore
from src.chatbot.llm_config import load_env, list_providers, set_active, get_active, get_llm_config, _provider_available, create_llm
from src.chatbot.engine import CrimeChatbot
from src.chatbot.case_intelligence import CaseIntelligence

load_env(PROJECT)

# Set analytics DATA_DIR before importing the router so queries hit the right DB
import api.analytics as _ana
_ana.DATA_DIR = PROJECT / "data"
from api.analytics import router as analytics_router

app = FastAPI(
    title="KSP Crime Intelligence API",
    description="Natural language queries over Karnataka crime databases",
    version="2.0.0",
)
app.include_router(analytics_router, prefix="/api/analytics")

# CORS: same-origin app, so only explicit trusted origins are allowed.
# Reflecting an arbitrary Origin with credentials would let any website a
# logged-in officer visits read the crime API. Override via CORS_ORIGINS
# (comma-separated) for the deployed Catalyst domain.
_default_origins = "http://localhost:8000,http://127.0.0.1:8000"
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

bot = CrimeChatbot(data_dir=PROJECT / "data")
chat_store = ChatStore(PROJECT / "data" / "chats.db")
doc_store = DocStore(PROJECT / "data" / "case_docs.db")
case_intel = CaseIntelligence(PROJECT / "data" / "case_knowledge.db")
FRONTEND = PROJECT / "frontend"
_AUDIT_DB = PROJECT / "data" / "audit.db"


def _init_audit():
    conn = sqlite3.connect(_AUDIT_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, session_id TEXT, question TEXT,
        sql_generated TEXT, database TEXT, language TEXT
    )""")
    conn.commit()
    conn.close()


def _write_audit(session_id: str, question: str, sql: str, db: str, lang: str):
    try:
        conn = sqlite3.connect(_AUDIT_DB)
        conn.execute(
            "INSERT INTO audit_log(ts,session_id,question,sql_generated,database,language) VALUES(?,?,?,?,?,?)",
            (datetime.utcnow().isoformat(), session_id, question, sql, db, lang),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


_init_audit()


class ModelSelect(BaseModel):
    provider: str
    model: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None
    history: list[dict] = Field(default_factory=list)
    language: str = "en"  # "en" or "kn" (Kannada)
    use_docs: bool = True   # inject uploaded case-file context


class ChatResponseModel(BaseModel):
    answer: str
    sql: str
    database: str
    data: str
    source: str
    original_question: str
    normalized_question: str
    correction_note: str | None = None
    session_id: str | None = None
    session_title: str | None = None
    used_case_file: bool = False


class SessionCreate(BaseModel):
    title: str = "New chat"


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class MessageModel(BaseModel):
    id: int
    role: str
    content: str
    created_at: str
    metadata: dict | None = None


class SessionDetail(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageModel]


class HealthResponse(BaseModel):
    status: str
    databases: dict[str, bool]
    llm_enabled: bool
    mode: str
    llm_provider: str
    llm_model: str | None


@app.get("/api/health", response_model=HealthResponse)
def health():
    dbs = bot.db.available()
    cfg = bot.llm_status()
    llm = cfg["enabled"]
    mode = cfg["provider"] if llm else "fallback"
    return HealthResponse(
        status="ok" if any(dbs.values()) else "degraded",
        databases=dbs,
        llm_enabled=llm,
        mode=mode,
        llm_provider=cfg["provider"],
        llm_model=cfg["model"],
    )


@app.get("/api/sessions", response_model=list[SessionSummary])
def list_sessions(limit: int = 50):
    sessions = chat_store.list_sessions(limit=min(limit, 100))
    return [
        SessionSummary(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=s.message_count,
        )
        for s in sessions
    ]


@app.post("/api/sessions", response_model=SessionSummary)
def create_session(body: SessionCreate | None = None):
    title = body.title if body else "New chat"
    session = chat_store.create_session(title=title)
    return SessionSummary(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0,
    )


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str):
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = chat_store.get_messages(session_id)
    return SessionDetail(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            MessageModel(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                metadata=m.metadata,
            )
            for m in messages
        ],
    )


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    if not chat_store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponseModel)
def chat(req: ChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if not any(bot.db.available().values()):
        raise HTTPException(status_code=503, detail="No crime databases found in data/")

    session_id = req.session_id
    session_title = None

    if session_id:
        session = chat_store.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        history = chat_store.get_history(session_id, limit=20)
    else:
        session = chat_store.create_session()
        session_id = session.id
        history = req.history or []

    chat_store.add_message(session_id, "user", message)
    session_title = chat_store.auto_title_from_message(session_id, message)

    # Rolling summary: when session grows > 20 messages, compact the oldest half
    total_msgs = chat_store.message_count(session_id)
    if total_msgs > 20 and total_msgs % 10 == 1:
        all_msgs = chat_store.get_messages(session_id)
        old_turns = [{"role": m.role, "content": m.content} for m in all_msgs[:-10]]
        new_summary = bot.agent.compact_history(old_turns)
        if new_summary:
            chat_store.set_summary(session_id, new_summary)

    # Prepend Kannada instruction if language==kn
    ask_message = message
    if req.language == "kn":
        ask_message = f"[Respond in Kannada language. Question in Kannada follows] {message}"

    # Inject case-file context if docs are attached to this session
    doc_context = ""
    if req.use_docs and session_id:
        doc_context = doc_store.get_context(session_id, message)
        if doc_context:
            ask_message = (
                f"{ask_message}\n\n"
                f"[CASE FILE CONTEXT — use this to answer the question above]\n{doc_context}"
            )

    try:
        resp = bot.ask(ask_message, history=history)
    except Exception as e:
        err = str(e)
        print(f"[chat error] {err}", file=sys.stderr)
        # Auto-fallback: if active provider hits quota/not-found, switch to Groq
        if any(x in err for x in ("429", "RESOURCE_EXHAUSTED", "quota", "NOT_FOUND", "404")):
            if _provider_available("groq"):
                set_active("groq", "llama-3.3-70b-versatile")
                bot._llm_checked = False  # force re-check
                try:
                    resp = bot.ask(ask_message, history=history)
                except Exception as e2:
                    print(f"[chat fallback error] {e2}", file=sys.stderr)
                    raise HTTPException(status_code=500, detail="The AI service is temporarily unavailable. Please try again.") from e2
            else:
                raise HTTPException(status_code=429, detail="AI provider quota exceeded and no fallback is configured.") from e
        else:
            raise HTTPException(status_code=500, detail="The AI service could not process that request. Please try again.") from e

    _write_audit(session_id, message, resp.sql, resp.database, req.language)

    assistant_meta = {
        "sql": resp.sql,
        "database": resp.database,
        "source": resp.source,
        "correction_note": resp.correction_note,
        "used_case_file": bool(doc_context),
    }
    chat_store.add_message(session_id, "assistant", resp.answer, metadata=assistant_meta)

    if not session_title:
        updated = chat_store.get_session(session_id)
        session_title = updated.title if updated else None

    return ChatResponseModel(
        answer=resp.answer,
        sql=resp.sql,
        database=resp.database,
        data=resp.data,
        source=resp.source,
        original_question=resp.original_question or message,
        normalized_question=resp.normalized_question or message,
        correction_note=resp.correction_note,
        session_id=session_id,
        session_title=session_title,
        used_case_file=bool(doc_context),
    )


# ── Model management ──────────────────────────────────────────────────────

@app.get("/api/models")
def get_models():
    return {"providers": list_providers(), "active": get_llm_config()}


@app.post("/api/models/select")
def select_model(body: ModelSelect):
    set_active(body.provider, body.model)
    cfg = get_llm_config()
    return {"ok": True, "active": cfg}


# ── Document / case-file endpoints ─────────────────────────────────────────

_MAX_UPLOAD = 20 * 1024 * 1024  # 20 MB

@app.post("/api/upload")
async def upload_file(session_id: str, file: UploadFile = File(...)):
    allowed = {".pdf", ".docx", ".doc", ".txt", ".md", ".csv"}
    from pathlib import PurePosixPath
    ext = PurePosixPath(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not supported. Use PDF, DOCX, TXT.")

    # Reject early on the declared size so a huge body isn't read into memory.
    declared = file.size if getattr(file, "size", None) is not None else None
    if declared is not None and declared > _MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    # Read with a hard cap: stop at limit+1 bytes instead of buffering everything.
    data = b""
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        data += chunk
        if len(data) > _MAX_UPLOAD:
            raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    result = doc_store.save(session_id, file.filename or "upload", data)
    return result


@app.get("/api/docs/{session_id}")
def list_session_docs(session_id: str):
    return {"docs": doc_store.list_docs(session_id)}


@app.delete("/api/docs/{session_id}/{doc_id}")
def delete_doc(session_id: str, doc_id: int):
    ok = doc_store.delete(session_id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}


@app.get("/api/audit")
def audit_log(limit: int = 100):
    conn = sqlite3.connect(_AUDIT_DB)
    rows = conn.execute(
        "SELECT id, ts, session_id, question, sql_generated, database, language "
        "FROM audit_log ORDER BY id DESC LIMIT ?", (min(limit, 500),)
    ).fetchall()
    conn.close()
    return {"logs": [
        {"id": r[0], "ts": r[1], "session_id": r[2], "question": r[3],
         "sql": r[4], "database": r[5], "language": r[6]}
        for r in rows
    ]}


# ── Case Intelligence endpoints ────────────────────────────────────────────

class CaseSolverRequest(BaseModel):
    facts: str = Field(..., min_length=10, max_length=5000,
                       description="Free-text description of the case facts")
    use_llm: bool = True


@app.post("/api/case-solver")
def solve_case(req: CaseSolverRequest):
    llm = create_llm() if req.use_llm else None
    brief = case_intel.build_investigation_brief(req.facts, llm=llm)
    similar = case_intel.search_similar(req.facts, limit=5)
    return {
        "brief": brief,
        "similar_cases": [
            {
                "title": c["title"],
                "year": c["year"],
                "location": c["location"],
                "crime_type": c["crime_type"],
                "breakthrough": c["breakthrough"],
                "outcome": c["outcome"],
            }
            for c in similar
        ],
    }


@app.get("/api/case-solver/search")
def search_cases(q: str, limit: int = 10):
    results = case_intel.search_similar(q, limit=min(limit, 20))
    return {
        "results": [
            {
                "id": c["id"], "title": c["title"], "year": c["year"],
                "location": c["location"], "state": c["state"],
                "crime_type": c["crime_type"], "breakthrough": c["breakthrough"],
                "outcome": c["outcome"],
                "investigation_tips": json.loads(c["investigation_tips"] or "[]"),
            }
            for c in results
        ]
    }


@app.get("/api/case-solver/stats")
def case_stats():
    return case_intel.stats()


@app.get("/api/case-solver/{case_id}")
def get_case(case_id: int):
    conn = sqlite3.connect(case_intel.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM solved_cases WHERE id = ?", (case_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    d = dict(row)
    for field in ("key_evidence", "investigation_tips", "tags"):
        try:
            d[field] = json.loads(d[field] or "[]")
        except Exception:
            d[field] = []
    return d


# ── Ollama local model management ─────────────────────────────────────────

class OllamaPullRequest(BaseModel):
    model: str


@app.get("/api/ollama/status")
def ollama_status():
    import socket
    # Fast socket check first — avoids hanging on refused connections
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.8)
    try:
        sock.connect(("127.0.0.1", 11434))
        sock.close()
    except Exception:
        return {"running": False, "models": []}
    # Port open — fetch model list
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as resp:
            data = _json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        return {"running": True, "models": models}
    except Exception:
        return {"running": True, "models": []}


@app.post("/api/ollama/pull")
def ollama_pull(body: OllamaPullRequest):
    import re, subprocess
    name = body.model.strip()
    if not name or not re.match(r'^[\w./:-]+$', name):
        raise HTTPException(status_code=400, detail="Invalid model name")
    try:
        subprocess.Popen(["ollama", "pull", name],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "message": f"Pulling {name} in the background — check Ollama terminal for progress"}
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Ollama binary not found. Install from https://ollama.com")


# ── Dedicated web search endpoint ─────────────────────────────────────────

@app.get("/api/web-search")
def web_search_endpoint(q: str):
    from src.chatbot.rag.web_search import search_web
    if not q.strip():
        raise HTTPException(status_code=400, detail="Empty query")
    results = search_web(q, max_results=5, bare=True)
    return {"query": q, "results": results or "No results found for this query."}


# ── Voice input (server-side speech-to-text via Groq Whisper) ──────────────
# The browser's Web Speech API streams audio to a cloud service that many
# networks/regions block, so mic capture succeeds but no transcript returns.
# Groq Whisper runs on the same endpoint the app already uses for the LLM, so
# it works wherever the app works — and transcribes Kannada natively.

_GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_STT_MODEL = os.getenv("STT_MODEL", "whisper-large-v3")
_MAX_AUDIO = 25 * 1024 * 1024  # Groq's audio upload ceiling


def _groq_key() -> str:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if key:
        return key
    # app-config also sets OPENAI_API_KEY to the Groq key when provider=groq
    alt = (os.getenv("OPENAI_API_KEY") or "").strip()
    return alt if alt.startswith("gsk_") else ""


@app.post("/api/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...), language: str = "en"):
    key = _groq_key()
    if not key:
        raise HTTPException(status_code=503,
                            detail="Voice input needs a Groq API key (set GROQ_API_KEY).")

    audio = b""
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        audio += chunk
        if len(audio) > _MAX_AUDIO:
            raise HTTPException(status_code=413, detail="Audio too long (max ~25 MB).")
    if not audio:
        raise HTTPException(status_code=400, detail="No audio received.")

    lang = "kn" if language == "kn" else "en"
    import requests
    try:
        r = requests.post(
            _GROQ_STT_URL,
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (file.filename or "voice.webm", audio,
                            file.content_type or "audio/webm")},
            data={"model": _GROQ_STT_MODEL, "language": lang,
                  "response_format": "json", "temperature": "0"},
            timeout=45,
        )
    except Exception as e:
        print(f"[voice transcribe] request failed: {e}", file=sys.stderr)
        raise HTTPException(status_code=502,
                            detail="Could not reach the transcription service.") from e

    if r.status_code != 200:
        print(f"[voice transcribe] groq {r.status_code}: {r.text[:300]}", file=sys.stderr)
        detail = "Transcription failed."
        if r.status_code in (401, 403):
            detail = "Transcription rejected — check the Groq API key."
        elif r.status_code == 429:
            detail = "Transcription rate-limited — try again in a moment."
        raise HTTPException(status_code=502, detail=detail)

    try:
        text = (r.json().get("text") or "").strip()
    except Exception:
        text = ""
    return {"text": text, "language": lang, "model": _GROQ_STT_MODEL}


# ── Database Browser ────────────────────────────────────────────────────────

_BROWSE_VIEWS: dict[str, dict[str, str]] = {
    "ksp_crime": {
        "FIR Records": (
            "SELECT f.fir_id as id, f.fir_number, d.name as district, "
            "ps.name as station, ch.name as crime, f.date_registered, f.year, f.month, f.status "
            "FROM fir_records f "
            "LEFT JOIN police_stations ps ON ps.station_id=f.station_id "
            "LEFT JOIN crime_heads ch ON ch.crime_head_id=f.crime_head_id "
            "LEFT JOIN districts d ON d.district_id=ps.district_id"
        ),
        "Criminals": (
            "SELECT c.criminal_id as id, c.name, c.alias, c.age, c.gender, d.name as district, c.status "
            "FROM criminals c LEFT JOIN districts d ON d.district_id=c.district_id"
        ),
        "Police Stations": (
            "SELECT ps.station_id as id, ps.name, ps.station_code, d.name as district "
            "FROM police_stations ps LEFT JOIN districts d ON d.district_id=ps.district_id"
        ),
        "Crime Categories": "SELECT crime_head_id as id, name, category, ipc_section, severity FROM crime_heads",
        "Districts": "SELECT district_id as id, name, zone, population FROM districts",
        "NCRB City Stats": "SELECT stat_id as id, city, state, year, total_cases, ipc_cases, crime_rate FROM ncrb_city_stats",
    },
    "criminal": {
        "Accused Persons": (
            "SELECT accused_id as id, fir_id, accused_name, age, gender, "
            "caste_category, was_arrested, was_convicted FROM accused_with_names"
        ),
        "FIR Details": (
            "SELECT f.fir_id as id, f.fir_year, f.fir_month, d.name as district, ch.name as crime "
            "FROM fir_details f "
            "LEFT JOIN districts d ON d.district_id=f.district_id "
            "LEFT JOIN crime_heads ch ON ch.head_id=f.crime_head_id"
        ),
        "Criminal Profiles": (
            "SELECT profile_id as id, district_name, village_area_name, "
            "primary_crime_head, total_firs, total_accused FROM criminal_profiles"
        ),
        "Persons": "SELECT person_id as id, name, alias, age, gender, occupation FROM persons",
    },
    "cases": {
        "Court Cases": (
            "SELECT ddl_case_id as id, linked_fir_id, year, state_name, district_name, "
            "court_name, type_name_s FROM cases_with_fir"
        ),
    },
    "fir": {
        "FIR Records": (
            "SELECT cm.CaseMasterID AS id, cm.CrimeNo AS fir_number, "
            "d.DistrictName AS district, u.UnitName AS station, "
            "csh.CrimeHeadName AS crime, cm.CrimeRegisteredDate AS date_registered, "
            "csm.CaseStatusName AS status "
            "FROM CaseMaster cm "
            "JOIN Unit u ON cm.PoliceStationID = u.UnitID "
            "JOIN District d ON u.DistrictID = d.DistrictID "
            "LEFT JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID "
            "LEFT JOIN CaseStatusMaster csm ON cm.CaseStatusID = csm.CaseStatusID"
        ),
        "Accused": (
            "SELECT a.AccusedMasterID AS id, a.AccusedName AS name, a.AgeYear AS age, "
            "CASE a.GenderID WHEN 1 THEN 'Male' WHEN 2 THEN 'Female' ELSE 'Other' END AS gender, "
            "a.District AS district, om.OccupationName AS occupation, a.Nationality "
            "FROM Accused a "
            "LEFT JOIN OccupationMaster om ON a.OccupationID = om.OccupationID "
            "WHERE a.AccusedName IS NOT NULL"
        ),
        "Police Stations": (
            "SELECT u.UnitID AS id, u.UnitName AS name, d.DistrictName AS district, "
            "ut.UnitTypeName AS type "
            "FROM Unit u "
            "JOIN District d ON u.DistrictID = d.DistrictID "
            "LEFT JOIN UnitType ut ON u.TypeID = ut.UnitTypeID "
            "WHERE u.TypeID IN (5, 6, 7, 8)"
        ),
        "Districts": (
            "SELECT DistrictID AS id, DistrictName AS name, Population AS population, "
            "Latitude AS latitude, Longitude AS longitude FROM District ORDER BY DistrictName"
        ),
        "Crime Gangs": (
            "SELECT g.GangID AS id, g.GangName AS name, g.Specialization AS specialization, "
            "d.DistrictName AS hq_district, g.ActiveSince AS active_since, "
            "COUNT(DISTINCT agl.AccusedMasterID) AS member_count "
            "FROM CrimeGang g "
            "LEFT JOIN District d ON d.DistrictID = g.HomeDistrictID "
            "LEFT JOIN AccusedGangLink agl ON agl.GangID = g.GangID "
            "GROUP BY g.GangID, g.GangName, g.Specialization, d.DistrictName, g.ActiveSince"
        ),
        "Victims": (
            "SELECT v.VictimMasterID AS id, v.VictimName AS name, v.AgeYear AS age, "
            "CASE v.GenderID WHEN 1 THEN 'Male' WHEN 2 THEN 'Female' ELSE 'Other' END AS gender, "
            "d.DistrictName AS district, cm.CrimeNo AS fir_number "
            "FROM Victim v "
            "JOIN CaseMaster cm ON v.CaseMasterID = cm.CaseMasterID "
            "JOIN Unit u ON cm.PoliceStationID = u.UnitID "
            "JOIN District d ON u.DistrictID = d.DistrictID "
            "WHERE v.VictimName IS NOT NULL"
        ),
    },
}


@app.get("/api/browse/{db}/schema")
def browse_schema(db: str):
    if db not in _BROWSE_VIEWS:
        raise HTTPException(status_code=404, detail="Database not found")
    return {"db": db, "views": list(_BROWSE_VIEWS[db].keys())}


@app.get("/api/browse/{db}/{view}")
def browse_view(db: str, view: str, page: int = 1, limit: int = 100, q: str = ""):
    view = unquote(view)
    if db not in _BROWSE_VIEWS or view not in _BROWSE_VIEWS[db]:
        raise HTTPException(status_code=404, detail="Not found")

    limit = min(max(limit, 1), 200)
    page = max(page, 1)
    offset = (page - 1) * limit
    base = _BROWSE_VIEWS[db][view]

    try:
        if db == "ksp_crime":
            conn = sqlite3.connect(str(bot.db.ksp_path))
            try:
                sample = _pd.read_sql_query(f"SELECT * FROM ({base}) LIMIT 0", conn)
                cols = list(sample.columns)
                if q:
                    cond = " OR ".join(f'CAST("{c}" AS TEXT) LIKE ?' for c in cols)
                    p = [f"%{q}%"] * len(cols)
                    total = conn.execute(f"SELECT COUNT(*) FROM ({base}) WHERE {cond}", p).fetchone()[0]
                    df = _pd.read_sql_query(
                        f"SELECT * FROM ({base}) WHERE {cond} ORDER BY 1 LIMIT {limit} OFFSET {offset}",
                        conn, params=p
                    )
                else:
                    total = conn.execute(f"SELECT COUNT(*) FROM ({base})").fetchone()[0]
                    df = _pd.read_sql_query(f"SELECT * FROM ({base}) ORDER BY 1 LIMIT {limit} OFFSET {offset}", conn)
            finally:
                conn.close()
        else:
            if db == "fir":
                path = bot.db.fir_path
            elif db == "criminal":
                path = bot.db.criminal_path
            else:
                path = bot.db.cases_path
            conn = _duckdb.connect(str(path), read_only=True)
            try:
                desc = conn.execute(f"SELECT * FROM ({base}) LIMIT 0").description
                cols = [c[0] for c in desc]
                if q:
                    cond = " OR ".join(f'CAST("{c}" AS VARCHAR) ILIKE ?' for c in cols)
                    p = [f"%{q}%"] * len(cols)
                    total = conn.execute(f"SELECT COUNT(*) FROM ({base}) WHERE {cond}", p).fetchone()[0]
                    df = conn.execute(
                        f"SELECT * FROM ({base}) WHERE {cond} ORDER BY 1 LIMIT {limit} OFFSET {offset}", p
                    ).df()
                else:
                    total = conn.execute(f"SELECT COUNT(*) FROM ({base})").fetchone()[0]
                    df = conn.execute(f"SELECT * FROM ({base}) ORDER BY 1 LIMIT {limit} OFFSET {offset}").df()
            finally:
                conn.close()
    except Exception as exc:
        # Don't leak internal SQL / engine errors to the client.
        print(f"[browse_view error] db={db} view={view}: {exc}", file=sys.stderr)
        raise HTTPException(status_code=500, detail="Could not load records for this view.") from exc

    return {
        "db": db,
        "view": view,
        "total": int(total),
        "page": page,
        "limit": limit,
        "pages": max(1, (int(total) + limit - 1) // limit),
        "columns": list(df.columns),
        "rows": df.fillna("").astype(str).values.tolist(),
    }


@app.get("/")
def index():
    index_path = FRONTEND / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
